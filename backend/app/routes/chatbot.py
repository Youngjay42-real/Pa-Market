"""Chatbot HTTP API — implements docs/CHATBOT_CONTRACT.md exactly.

Endpoints (versioned REST under /api/v1):
    GET  /api/v1/chatbot/health
    POST /api/v1/chatbot/sessions
    POST /api/v1/chatbot/sessions/<sid>/messages
    GET  /api/v1/chatbot/sessions/<sid>/messages
    POST /api/v1/chatbot/sessions/<sid>/close

Developer 3 (AI Chatbot Engineer) owns this file per the master project prompt.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from flask import Blueprint, Response, g, jsonify, request

from ..extensions import get_chatbot_service
from ..chatbot import ChatbotError
from ..chatbot.database import healthcheck as database_health

blueprint = Blueprint("chatbot", __name__)

ASSISTANT_NAME = "StandProof Market Assistant"


def _json(data: Dict[str, Any], status: int = 200) -> Response:
    response = jsonify(data)
    response.status_code = status
    return response


def _bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def _remote_addr() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------


@blueprint.get("/health")
def health():
    service = get_chatbot_service()
    db_ok = database_health()
    return _json(
        {
            "status": "ok",
            "assistant": {
                "name": ASSISTANT_NAME,
                "llmProvider": service.llm_name,
                "database": "ok" if db_ok else "error",
            },
        }
    )


# --------------------------------------------------------------------------
# sessions
# --------------------------------------------------------------------------


@blueprint.post("/sessions")
def create_session():
    body = request.get_json(silent=True) or {}
    identity_payload = body.get("identity")
    if identity_payload is not None and not isinstance(identity_payload, dict):
        raise ChatbotError("invalid_request", "identity must be an object.", 400)

    service = get_chatbot_service()
    result = service.create_session(identity_payload, remote_addr=_remote_addr())
    return _json(result)


# --------------------------------------------------------------------------
# messages
# --------------------------------------------------------------------------


@blueprint.post("/sessions/<session_id>/messages")
def send_message(session_id: str):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("content"), str):
        raise ChatbotError("invalid_request", "content (string) is required.", 400)
    if not body.get("content", "").strip():
        raise ChatbotError("invalid_request", "Message text is required.", 400)

    service = get_chatbot_service()
    result = service.send_message(_bearer_token(), session_id, body.get("content", ""))
    return _json(result)


@blueprint.get("/sessions/<session_id>/messages")
def message_history(session_id: str):
    service = get_chatbot_service()
    result = service.history(_bearer_token(), session_id)
    return _json(result)


@blueprint.post("/sessions/<session_id>/close")
def close_session(session_id: str):
    service = get_chatbot_service()
    result = service.close_session(_bearer_token(), session_id)
    return _json(result)


# --------------------------------------------------------------------------
# error mapping — never leak internals/stack traces to the client
# --------------------------------------------------------------------------


@blueprint.errorhandler(ChatbotError)
def handle_chatbot_error(error: ChatbotError):
    response = jsonify(error.as_dict())
    response.status_code = error.http_status
    if error.retry_after:
        response.headers["Retry-After"] = str(error.retry_after)
    return response


@blueprint.errorhandler(404)
def handle_not_found(_error):
    return jsonify({"error": {"code": "invalid_request", "message": "Unknown endpoint."}}), 404
