"""ChatbotService — turn orchestration.

Responsibilities:
* create sessions bound to a verified identity (or a guest)
* run the structured tool-calling loop with an LLM client
* persist every user, assistant and tool turn (chat_session / chat_message)
* keep the assistant honest: verified flags, degraded fallbacks, refusal paths

Security notes:
* The identity is verified once at session creation; afterwards the signed chat
  token agrees with the stored session record, and tool scoping always comes from
  that server-side record — never from client-supplied parameters.
* The service is strictly read-only towards application tables.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import prompts as prompt_lib
from .database import session_scope
from .identity import Identity, issue_chat_token, read_chat_token, verify_identity
from .llm import LLMError, LLMResult, llm_client_from_env
from .models import ChatMessage, ChatSession
from .permissions import AccessContext
from .ratelimit import DEFAULT_MESSAGE_RULE, DEFAULT_SESSION_RULE, RateLimiter, RateLimitExceeded
from .tools import DATABASE_TOOLS, TOOL_SCHEMAS, execute_tool

log = logging.getLogger("standproof.chatbot")

MAX_TURNS_PER_MESSAGE = 5          # LLM round-trips per user message
MAX_CONVERSATION_CONTEXT = 12      # previous messages replayed to the LLM
MAX_CONTENT_LENGTH = 2000
TOOL_TRACE_MAX_CHARS = 6000

ILLEGAL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class ChatbotError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400, retry_after: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retry_after = retry_after

    def as_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


class ChatbotService:
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        session_rule: Optional[Any] = None,
        message_rule: Optional[Any] = None,
        max_tool_turns: int = MAX_TURNS_PER_MESSAGE,
    ) -> None:
        self._llm = llm_client or llm_client_from_env()
        self._rate = RateLimiter()
        self._session_rule = session_rule or DEFAULT_SESSION_RULE
        self._message_rule = message_rule or DEFAULT_MESSAGE_RULE
        self._max_tool_turns = max_tool_turns

    @property
    def llm_name(self) -> str:
        """Provider label surfaced on the health endpoint (contract §4.1)."""
        return getattr(self._llm, "name", "unknown")

    # ------------------------------------------------------------------
    # sessions
    # ------------------------------------------------------------------

    def create_session(self, identity_payload: Optional[dict], remote_addr: str = "") -> dict:
        try:
            self._rate.check(self._session_rule, remote_addr or "unknown-ip")
        except RateLimitExceeded as exc:
            raise ChatbotError("rate_limited", "Too many sessions created; please retry later.", 429, exc.retry_after_seconds)

        with session_scope() as session:
            identity, error = verify_identity(session, identity_payload)
            if error or identity is None:
                raise ChatbotError("identity_invalid", "We could not verify this market account. Please log in again.", 401)

            record = ChatSession(
                kind=identity.kind,
                user_id=identity.user_id,
                user_name=identity.display_name,
                user_phone=identity.phone,
                user_role=identity.role if identity.is_verified else "guest",
                user_nrc=identity.nrc,
                user_business_type=identity.business_type,
            )
            session.add(record)
            session.flush()

            greeting = prompt_lib.greeting(identity.display_name, record.user_role)
            greeting_row = ChatMessage(
                session_id=record.id, role="assistant", content=greeting, verified=False, degraded=False
            )
            session.add(greeting_row)
            session.flush()
            record.message_count = 1

            return {
                "sessionId": record.id,
                "chatToken": issue_chat_token(identity),
                "identity": identity.public_dict(),
                "greeting": greeting,
                "suggestedPrompts": prompt_lib.suggested_prompts(record.user_role),
            }

    # ------------------------------------------------------------------
    # messaging
    # ------------------------------------------------------------------

    def send_message(self, token: str, session_id: str, content: str) -> dict:
        identity = read_chat_token(token or "")
        if identity is None:
            raise ChatbotError("chat_token_invalid", "Your chat session expired. Please reopen the assistant.", 401)

        clean = ILLEGAL_PATTERN.sub("", str(content or "")).strip()
        if not clean:
            raise ChatbotError("invalid_request", "Message text is required.", 400)
        if len(clean) > MAX_CONTENT_LENGTH:
            raise ChatbotError("message_too_long", "Messages are limited to 2000 characters.", 413)

        user_message, assistant_message, suggestions = self._run_turn(identity, session_id, clean)
        return {
            "userMessage": user_message,
            "assistantMessage": assistant_message,
            "suggestedPrompts": suggestions,
        }

    def history(self, token: str, session_id: str, limit: int = 200) -> dict:
        identity = read_chat_token(token or "")
        if identity is None:
            raise ChatbotError("chat_token_invalid", "Your chat session expired. Please reopen the assistant.", 401)

        with session_scope() as session:
            record = self._load_session(session, session_id)
            if not self._owns(record, identity):
                raise ChatbotError("session_not_found", "Chat session not found.", 404)
            messages = (
                session.query(ChatMessage)
                .filter(
                    ChatMessage.session_id == session_id,
                    ChatMessage.role.in_(["user", "assistant"]),  # transcript only; tool turns stay in the audit store
                )
                .order_by(ChatMessage.id)
                .limit(limit)
                .all()
            )
            return {
                "sessionId": session_id,
                "identity": identity.public_dict(),
                "messages": [m.as_client_dict() for m in messages],
            }

    def close_session(self, token: str, session_id: str) -> dict:
        identity = read_chat_token(token or "")
        if identity is None:
            raise ChatbotError("chat_token_invalid", "Your chat session expired.", 401)
        with session_scope() as session:
            record = self._load_session(session, session_id)
            if not self._owns(record, identity):
                raise ChatbotError("session_not_found", "Chat session not found.", 404)
            record.closed = True
            return {"sessionId": session_id, "closed": True}

    # ------------------------------------------------------------------
    # the turn loop
    # ------------------------------------------------------------------

    def _run_turn(self, token_identity: Identity, session_id: str, content: str) -> Tuple[dict, dict, list]:
        with session_scope() as session:
            record = self._load_session(session, session_id)
            if not self._owns(record, token_identity):
                raise ChatbotError("session_not_found", "Chat session not found.", 404)
            if record.closed:
                raise ChatbotError("session_closed", "This chat was closed. Start a new conversation.", 409)

            try:
                self._rate.check(self._message_rule, session_id)
            except RateLimitExceeded as exc:
                raise ChatbotError("rate_limited", "You're sending messages too quickly. Please slow down a little.", 429, exc.retry_after_seconds)

            # The SERVER-SIDE record is the identity source of truth for scoping.
            attached = self._identity_for(record)

            history = self._llm_history(session, session_id)
            context = self._build_context(record, attached, history, content)

            user_row = ChatMessage(session_id=session_id, role="user", content=content)
            session.add(user_row)
            session.flush()

            verified = False
            degraded = False
            tools_used: List[str] = []
            try:
                reply, tools_used, tool_traces, any_ok = self._loop(session, attached, context)
                verified = any_ok
            except LLMError:
                log.warning("LLM provider failed; returning degraded reply", exc_info=True)
                reply = prompt_lib.FALLBACK_DEGRADED
                degraded = True
                tool_traces = []

            # persist each tool turn for the chatbot audit trail (contract §2)
            for trace_name, trace_payload in tool_traces:
                payload_json = json.dumps(trace_payload, default=str)[:TOOL_TRACE_MAX_CHARS]
                session.add(
                    ChatMessage(
                        session_id=session_id,
                        role="tool",
                        content="",
                        tool_name=trace_name,
                        tool_payload=payload_json,
                        verified=False,
                        degraded=False,
                    )
                )

            assistant_row = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=reply,
                verified=verified and not degraded,
                degraded=degraded,
                tool_name=",".join(tools_used) if tools_used else None,
            )
            session.add(assistant_row)
            session.flush()
            record.message_count = (record.message_count or 0) + 2

            return (
                user_row.as_client_dict(),
                assistant_row.as_client_dict(),
                prompt_lib.suggested_prompts(record.user_role),
            )

    def _loop(
        self, session: Session, attached: Identity, context: List[dict]
    ) -> Tuple[str, List[str], List[Tuple[str, dict]], bool]:
        """Run the LLM + tool loop until a plain answer appears.

        Returns ``(final_text, tools_used, tool_traces, any_tool_ok)``.
        """
        messages: List[dict] = list(context)
        tools_used: List[str] = []
        tool_traces: List[Tuple[str, dict]] = []
        any_tool_ok = False

        for _ in range(self._max_tool_turns):
            result: LLMResult = self._llm.complete(messages, tools=TOOL_SCHEMAS)

            if result.has_tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": result.content,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(call.arguments or {}),
                                },
                            }
                            for call in result.tool_calls
                        ],
                    }
                )
                for call in result.tool_calls:
                    with session_scope() as tool_session:
                        outcome = execute_tool(
                            AccessContext(identity=attached, session=tool_session),
                            call.name,
                            call.arguments or {},
                        )
                    tool_traces.append((call.name, outcome))
                    tools_used.append(call.name)
                    if outcome.get("ok") is True and call.name in DATABASE_TOOLS:
                        any_tool_ok = True
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": json.dumps(outcome, default=str),
                        }
                    )
                continue

            text = (result.content or "").strip()
            if text:
                return text, tools_used, tool_traces, any_tool_ok

        raise LLMError("exceeded tool loop budget")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _load_session(self, session: Session, session_id: str) -> ChatSession:
        record = session.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        ).scalar_one_or_none()
        if record is None:
            raise ChatbotError("session_not_found", "Chat session not found.", 404)
        return record

    def _owns(self, record: ChatSession, identity: Identity) -> bool:
        identity_role = identity.role if identity.is_verified else "guest"
        return record.user_id == identity.user_id and record.user_role == identity_role

    @staticmethod
    def _identity_for(record: ChatSession) -> Identity:
        return Identity(
            kind=record.kind,
            user_id=record.user_id,
            full_name=record.user_name,
            phone=record.user_phone,
            role=record.user_role if record.user_role != "guest" else "guest",
            nrc=record.user_nrc,
            business_type=record.user_business_type,
        )

    @staticmethod
    def _llm_history(session: Session, session_id: str) -> List[dict]:
        """Replayable conversation history (user + assistant text only)."""
        rows = (
            session.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role.in_(["user", "assistant"]))
            .order_by(ChatMessage.id.desc())
            .limit(MAX_CONVERSATION_CONTEXT)
            .all()
        )
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    @staticmethod
    def _build_context(record: ChatSession, attached: Identity, history: List[dict], content: str) -> List[dict]:
        system = prompt_lib.system_prompt(attached.role if attached.is_verified else "guest")
        context: List[dict] = [{"role": "system", "content": system}]
        context.extend(history)
        context.append({"role": "user", "content": content})
        return context
