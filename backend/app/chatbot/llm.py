"""LLM clients for the Market Assistant.

Two implementations behind one tiny interface:

* ``OpenAICompatibleLLMClient`` — real structured function calling against any
  OpenAI-compatible ``/chat/completions`` endpoint (OpenAI, OpenRouter, Groq,
  Azure-style gateways, local vLLM/Ollama servers).
* ``RuleBasedLLMClient`` — a clearly-labelled deterministic assistant used when no
  API key/provider is configured. It emits exactly the same tool-call shapes so the
  whole service (and the tests, and the judges' demo) work offline. The provider
  name is surfaced on the health endpoint as ``"llmProvider": "mock"`` — the mock is
  never passed off as a real integration.

Provider selection: env ``CHATBOT_LLM_PROVIDER`` = mock | openai | openrouter |
groq | custom (+ ``CHATBOT_LLM_API_KEY``, ``CHATBOT_LLM_MODEL``, ``CHATBOT_LLM_BASE_URL``).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import requests

DEFAULT_TIMEOUT_SECONDS = 45
MAX_COMPLETION_ATTEMPTS = 2

PROVIDER_DEFAULTS = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-4o-mini"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.1-8b-instant"},
}


class LLMError(Exception):
    """Raised when a configured provider is unreachable or misbehaving."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResult:
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class BaseLLMClient:
    name = "base"

    def complete(
        self, messages: Sequence[dict], tools: Optional[List[dict]] = None
    ) -> LLMResult:  # pragma: no cover - interface
        raise NotImplementedError


# --------------------------------------------------------------------------
# OpenAI-compatible provider
# --------------------------------------------------------------------------


class OpenAICompatibleLLMClient(BaseLLMClient):
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, messages: Sequence[dict], tools: Optional[List[dict]] = None) -> LLMResult:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": 0.3,
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        last_error: Optional[Exception] = None
        for attempt in range(MAX_COMPLETION_ATTEMPTS):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                if response.status_code >= 500 and attempt + 1 < MAX_COMPLETION_ATTEMPTS:
                    time.sleep(0.4)
                    continue
                if response.status_code >= 400:
                    # never include response bodies/secrets in raised errors
                    raise LLMError(
                        f"LLM provider returned HTTP {response.status_code}."
                    )
                data = response.json()
                return self._parse(data)
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < MAX_COMPLETION_ATTEMPTS:
                    time.sleep(0.4)
                    continue
        raise LLMError("LLM provider is unreachable." if last_error else "LLM provider failed.")

    def _parse(self, data: dict) -> LLMResult:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("Unexpected response shape from provider.")

        calls: List[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function", {})
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
                if not isinstance(arguments, dict):
                    arguments = {}
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                ToolCall(
                    id=raw.get("id") or f"call_{len(calls) + 1}",
                    name=fn.get("name") or "",
                    arguments=arguments,
                )
            )
        return LLMResult(content=message.get("content"), tool_calls=calls)


# --------------------------------------------------------------------------
# Deterministic rule-based fallback (labelled "mock")
# --------------------------------------------------------------------------

_INTENT_APPLICATION = re.compile(r"application|allocation status|\bmy stand\b|\bmy position\b|queue position|where am i|my status", re.I)
_INTENT_PAYMENTS = re.compile(r"payment|receipt|paid|bill|levy|invoice", re.I)
_INTENT_NOTIFICATIONS = re.compile(r"notification|message|alert|news", re.I)
_INTENT_FINANCIALS = re.compile(r"savings|village banking|tax|sales|deposit|loan", re.I)
_INTENT_STATS = re.compile(r"statistic|stats|overview|summary|how is the market|how is the system|dashboard numbers", re.I)
_INTENT_QUEUE = re.compile(r"queue|pending applications|waiting list|who is next|next allocations", re.I)
_INTENT_ALLOCATIONS = re.compile(r"recent allocation|who was allocated|last allocated|allocation history|audit", re.I)
_INTENT_PENDING_VERIFY = re.compile(r"verification|verify|unconfirmed|awaiting|outstanding payment", re.I)
_INTENT_SUSPICIOUS = re.compile(r"suspicious|fraud|integrity|irregular|anomal|corrupt|abnormal|duplicate", re.I)
_INTENT_AVAILABILITY = re.compile(r"available|free stand|vacant|vacancy|occupancy|stands left|unoccupied", re.I)

_POLICY_TOPICS = {
    "allocation": re.compile(r"allocat|apply|application|process|requirements|how do i|register", re.I),
    "payments": re.compile(r"pay|charge|cost|fee|money", re.I),
    "permits": re.compile(r"permit|qr|license|licence", re.I),
    "verification": re.compile(r"verif|handover|hand over|inspect", re.I),
    "reports": re.compile(r"report|whistleblow|corruption|complain", re.I),
}

_INTENT_GREETING = re.compile(r"^\s*(hi|hello|hey|muli shani|good (morning|afternoon|evening))\b", re.I)
_INTENT_THANKS = re.compile(r"\b(thanks|thank you)\b", re.I)


def _roles(system_text: str) -> str:
    lowered = system_text.lower()
    if "authorised council administrator" in lowered:
        return "admin"
    if "logged-in vendor" in lowered:
        return "vendor"
    return "guest"


class RuleBasedLLMClient(BaseLLMClient):
    """Deterministic assistant. NOT the production LLM.

    Understands a fixed intent list, exactly like the real provider emits tool
    calls, then composes readable answers from the tool payloads the service
    returns. Every answer is grounded in tool output or explicit policy text.
    """

    name = "mock"

    def __init__(self, max_tool_rounds: int = 3):
        self._max_tool_rounds = max_tool_rounds

    def complete(self, messages: Sequence[dict], tools: Optional[List[dict]] = None) -> LLMResult:
        last = messages[-1] if messages else {}
        role = last.get("role")

        if role == "user":
            return self._route_user_message(messages)

        if role == "tool":
            return LLMResult(content=self._compose_from_tools(messages))

        # nothing sensible to say mid-loop
        return LLMResult(content="Let's continue — could you repose that question?")

    # -- routing ------------------------------------------------------------

    def _route_user_message(self, messages: Sequence[dict]) -> LLMResult:
        system_text = ""
        for message in messages:
            if message.get("role") == "system":
                system_text += message.get("content") or ""
        role = _roles(system_text)
        text = str(messages[-1].get("content") or "")

        if _INTENT_GREETING.search(text) or _INTENT_THANKS.search(text):
            return LLMResult(
                content=(
                    "Hello! I can explain how stand allocation, payments and permits work, "
                    "or check your own records when you're logged in. What can I help with?"
                )
            )

        # role-specific data intents first (personal data access)
        if role == "vendor":
            if _INTENT_APPLICATION.search(text):
                return self._tool_calls("get_my_application_status")
            if _INTENT_PAYMENTS.search(text) and not _INTENT_PENDING_VERIFY.search(text):
                return self._tool_calls("get_my_payments")
            if _INTENT_NOTIFICATIONS.search(text):
                return self._tool_calls("get_my_notifications")
            if _INTENT_FINANCIALS.search(text):
                return self._tool_calls("get_my_financials")

        if role == "admin":
            if _INTENT_SUSPICIOUS.search(text):
                return self._tool_calls("find_suspicious_activity")
            if _INTENT_QUEUE.search(text):
                return self._tool_calls("get_queue_summary")
            if _INTENT_PENDING_VERIFY.search(text) or (_INTENT_PAYMENTS.search(text) and re.search(r"pending|confirm|verif|waiting", text, re.I)):
                return self._tool_calls("list_pending_verifications")
            if _INTENT_ALLOCATIONS.search(text):
                return self._tool_calls("list_recent_allocations")
            if _INTENT_STATS.search(text) or re.search(r"how many", text, re.I):
                return self._tool_calls("get_application_statistics")

        # Any role may *ask* about integrity checks; the tool's permission layer
        # answers non-admins with a structured denial the assistant explains.
        if _INTENT_SUSPICIOUS.search(text):
            return self._tool_calls("find_suspicious_activity")

        # market-wide / public
        if _INTENT_AVAILABILITY.search(text) or re.search(r"how many stands", text, re.I):
            return self._tool_calls("get_market_overview")

        for topic, matcher in _POLICY_TOPICS.items():
            if matcher.search(text):
                return self._tool_calls("explain_market_policy", {"topic": topic})

        return LLMResult(
            content=(
                "I'm not sure I can answer that yet with verified records. I can help with:\n"
                "- checking your own application, payments or notifications (vendor login)\n"
                "- stand availability and how allocation, payments, permits or reporting work\n"
                "- market-wide summaries, audit activity and integrity flags (admin login)\n"
                "Try one of those, or use the suggested questions below."
            )
        )

    def _tool_calls(self, name: str, arguments: Optional[dict] = None) -> LLMResult:
        return LLMResult(
            tool_calls=[ToolCall(id=f"mock_{name}", name=name, arguments=arguments or {})]
        )

    # -- answer composition --------------------------------------------------

    def _compose_from_tools(self, messages: Sequence[dict]) -> str:
        results: List[tuple[str, dict]] = []
        pending_calls: Dict[str, str] = {}
        for message in messages[-8:]:
            if message.get("role") == "assistant":
                # OpenAI wire format: tool_calls: [{id, type, function:{name, arguments}}]
                for call in message.get("tool_calls", []) or []:
                    fn = call.get("function", {}) if isinstance(call, dict) else {}
                    pending_calls[str(call.get("id"))] = str(fn.get("name", "tool"))
            elif message.get("role") == "tool":
                try:
                    payload = json.loads(message.get("content") or "{}")
                except json.JSONDecodeError:
                    payload = {}
                results.append((pending_calls.get(str(message.get("tool_call_id")), "tool"), payload))

        sections = [self._render(name, payload) for name, payload in results]
        return "\n\n".join(part for part in sections if part)

    def _render(self, name: str, payload: dict) -> str:
        if not isinstance(payload, dict):
            return FALLBACK_GENERIC_TEXT

        if payload.get("denied"):
            polite = str(payload.get("error", "This information is restricted."))
            return f"{polite} You can ask me about stand availability, how allocation works, or your own records after logging in."

        if payload.get("ok") is False:
            return f"{payload.get('error', 'The records could not be read right now. Please try again shortly.')}"

        renderer = getattr(self, f"_render_{name}", None)
        if renderer:
            return renderer(payload)
        return FALLBACK_GENERIC_TEXT

    def _render_get_my_application_status(self, d: dict) -> str:
        if d.get("ok") is False:
            return str(d.get("error"))
        app = d.get("application", {})
        status = str(app.get("status", "unknown"))
        lines = ["From your verified application record:"]
        if status == "pending":
            lines.append(f"• Status: pending review — queue position {app.get('queuePosition')}.")
        elif status == "allocated":
            stand = d.get("stand") or {}
            lines.append(f"• Status: allocated — Stand {stand.get('id')} in {stand.get('zone')} ({stand.get('status')}).")
        else:
            lines.append(f"• Status: {status}.")
        if app.get("businessType"):
            lines.append(f"• Business type: {app.get('businessType')}.")
        if app.get("preferredZone"):
            lines.append(f"• Preferred zone: {app.get('preferredZone')}.")
        if app.get("appliedAgo"):
            lines.append(f"• Applied: {app.get('appliedAgo')}.")
        if status == "allocated":
            lines.append("Next step: complete payment and handover verification with the council team.")
        return "\n".join(lines)

    def _render_get_my_payments(self, d: dict) -> str:
        payments = d.get("payments") or []
        if not payments:
            return "There are no payment records on your account yet. A payment is only created after a stand is allocated to you."
        lines = [f"You have {d.get('count')} payment record(s); latest first (verified records):"]
        for p in payments:
            pending = " ⚠ awaiting verification" if p.get("status") == "pending" else ""
            receipt = f", receipt {p.get('receiptNo')}" if p.get("receiptNo") else ""
            lines.append(f"• {p.get('amount')} — {p.get('status')}{receipt} ({p.get('age')}){pending}")
        lines.append("Payment confirmation happens through the council verification screens, not in chat.")
        return "\n".join(lines)

    def _render_get_my_notifications(self, d: dict) -> str:
        if not d.get("total"):
            return "You have no notifications yet — they'll appear here when the council updates your application."
        lines = [f"You have {d.get('unread')} unread of {d.get('total')} notification(s). Latest:"]
        for n in (d.get("latest") or [])[:5]:
            lines.append(f"• {n.get('title')} — {str(n.get('message', ''))[:140]}")
        return "\n".join(lines)

    def _render_get_my_financials(self, d: dict) -> str:
        lines = ["Your financials (verified records):"]
        sales = d.get("dailySales") or {}
        lines.append(f"• Daily sales: {sales.get('recorded')} recorded, {sales.get('paidEntries')} paid, unpaid tax due {sales.get('unpaidTaxDue')}.")
        tax = d.get("latestTaxPayment")
        if tax:
            lines.append(f"• Latest tax payment: {tax.get('amount')} (receipt {tax.get('receiptNo')}, {tax.get('paidAt')}).")
        bank = d.get("villageBanking")
        if bank:
            lines.append(f"• Village banking ({bank.get('groupId')}): balance {bank.get('balance')} of goal {bank.get('savingsGoal')} at {bank.get('interestRate')}.")
        if not d.get("latestTaxPayment") and not d.get("villageBanking"):
            lines.append("No tax payments or village banking account on file yet.")
        return "\n".join(lines)

    def _render_get_market_overview(self, d: dict) -> str:
        stands = d.get("stands") or {}
        apps = d.get("applications") or {}
        lines = [
            f"Live market picture ({d.get('generatedAt')} — verified database counts):",
            f"• Stands: {stands.get('total')} total — {stands.get('available')} available, {stands.get('occupied')} occupied, {stands.get('reserved')} reserved, {stands.get('maintenance')} maintenance.",
        ]
        for zone in (stands.get("byZone") or [])[:5]:
            lines.append(f"• {zone.get('zone')}: {zone.get('available')} available of {zone.get('available') + zone.get('occupied', 0) + zone.get('reserved', 0) + zone.get('maintenance', 0)}.")
        lines.append(f"• Applications: {apps.get('pending')} pending, {apps.get('allocated')} allocated, {apps.get('rejected')} rejected.")
        lines.append(f"• Current queue depth: {d.get('queueDepth')} vendors.")
        return "\n".join(lines)

    def _render_get_application_statistics(self, d: dict) -> str:
        apps = d.get("applications") or {}
        occ = d.get("standOccupancy") or {}
        pay = d.get("payments") or {}
        lines = [f"Market-wide statistics ({d.get('generatedAt')} — verified records):"]
        lines.append(f"• Applications — pending {apps.get('pending', 0)}, allocated {apps.get('allocated', 0)}, rejected {apps.get('rejected', 0)}.")
        lines.append(f"• Stands — {occ.get('available', 0)} available, {occ.get('occupied', 0)} occupied, {occ.get('reserved', 0)} reserved, {occ.get('maintenance', 0)} under maintenance.")
        lines.append(f"• Payments — {pay.get('pending', 0)} pending, {pay.get('confirmed', 0)} confirmed, {pay.get('failed', 0)} failed.")
        mix = d.get("businessTypeMix") or {}
        if mix:
            top = ", ".join(f"{k} ({v})" for k, v in list(mix.items())[:4])
            lines.append(f"• Business mix: {top}.")
        lines.append(f"• Queue depth: {d.get('queueDepth')}.")
        return "\n".join(lines)

    def _render_get_queue_summary(self, d: dict) -> str:
        rows = d.get("pendingApplication") or []
        if not rows:
            return "The allocation queue is empty — no pending applications right now."
        lines = [f"Allocation queue — {d.get('queueDepth')} pending vendors (top {d.get('shown', len(rows))} shown):"]
        for r in rows:
            zone = f", prefers {r.get('preferredZone')}" if r.get("preferredZone") else ""
            lines.append(f"• #{r.get('queuePosition')} {r.get('vendorName')} — {r.get('businessType')}{zone}.")
        lines.append("Vendor contact details are in the admin dashboard (hidden in chat by design).")
        return "\n".join(lines)

    def _render_list_recent_allocations(self, d: dict) -> str:
        rows = d.get("allocations") or []
        if not rows:
            return "No stand allocations recorded in the audit log yet."
        lines = [f"{d.get('count')} allocation(s) on the audit trail; most recent {len(rows)}:"]
        for a in rows:
            actor = a.get("actor") or "unknown"
            lines.append(f"• {a.get('entityId')} — {a.get('action')} by {actor} ({a.get('age')}).")
        lines.append("An allocation only becomes final after handover verification and confirmed payment.")
        return "\n".join(lines)

    def _render_list_pending_verifications(self, d: dict) -> str:
        pays = d.get("pendingPayments") or []
        reps = d.get("recentCorruptionReports") or []
        lines = [f"{d.get('pendingPaymentCount')} payment(s) awaiting verification; oldest first:"]
        for p in pays:
            hours = p.get("waitingHours")
            age = f"{hours} h" if hours is not None else "?"
            lines.append(f"• {p.get('paymentId')} — {p.get('amount')} via {p.get('method')} (waiting {age}).")
        if reps:
            lines.append(f"{len(reps)} recent corruption report(s):")
            for r in reps:
                lines.append(f"• {r.get('category')} at {r.get('location') or 'unspecified location'} ({r.get('age')}).")
        lines.append("Confirmations happen in the admin verification screens — the assistant cannot verify payments.")
        return "\n".join(lines)

    def _render_find_suspicious_activity(self, d: dict) -> str:
        if not d.get("findingCount"):
            return "The rule-based checks found no suspicious patterns right now."
        lines = [f"Integrity flags ({d.get('findingCount')} pattern types need review):"]
        for f in d.get("findings") or []:
            lines.append(f"• {f.get('pattern')} — severity {f.get('severity')}, {f.get('occurrences')} occurrence(s).")
        lines.append("Flags are indicators for human review; conclusions require the admin dashboard.")
        return "\n".join(lines)

    def _render_explain_market_policy(self, d: dict) -> str:
        lines = [str(d.get("summary", "")).strip()]
        for point in d.get("points") or []:
            lines.append(f"• {point}")
        return "\n".join(lines)


FALLBACK_GENERIC_TEXT = (
    "Here's what the verified records show, summarised: the data was retrieved successfully but "
    "I couldn't format a full summary. Please ask again or use the admin dashboard for the complete view."
)


# --------------------------------------------------------------------------
# provider selection
# --------------------------------------------------------------------------


def llm_client_from_env(env: Optional[Dict[str, str]] = None) -> BaseLLMClient:
    environment = dict(env or os.environ)
    provider = (environment.get("CHATBOT_LLM_PROVIDER") or "mock").strip().lower()

    if provider == "mock":
        return RuleBasedLLMClient()

    defaults = PROVIDER_DEFAULTS.get(provider)
    base_url = environment.get("CHATBOT_LLM_BASE_URL") or (defaults or {}).get("base_url")
    model = environment.get("CHATBOT_LLM_MODEL") or (defaults or {}).get("model")
    api_key = environment.get("CHATBOT_LLM_API_KEY") or ""

    if provider == "custom" and not base_url:
        return RuleBasedLLMClient()
    if not defaults and provider != "custom":
        return RuleBasedLLMClient()
    if not api_key:
        return RuleBasedLLMClient()
    if not base_url or not model:
        return RuleBasedLLMClient()

    return OpenAICompatibleLLMClient(base_url=base_url, api_key=api_key, model=model)


def provider_label(client: BaseLLMClient) -> str:
    return client.name
