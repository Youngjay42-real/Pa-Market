"""Process-wide singletons for the chatbot service.

Integration note (Developer 3 → backend lead): the Flask factory wires this module;
when the full backend lands, the backend lead can replace the lazy singleton with
their Flask app-context wiring (e.g. ``current_app.extensions["standproof_chat"]``).
"""

from __future__ import annotations

from typing import Optional

from .chatbot import ChatbotService

_chatbot_service: Optional[ChatbotService] = None


def get_chatbot_service() -> ChatbotService:
    global _chatbot_service
    if _chatbot_service is None:
        _chatbot_service = ChatbotService()
    return _chatbot_service


def set_chatbot_service(service: ChatbotService) -> None:
    """Used by tests (and later by the backend lead's factory) to inject clients."""
    global _chatbot_service
    _chatbot_service = service
