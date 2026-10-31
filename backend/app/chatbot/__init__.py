"""StandProof chatbot package (Developer 3 — AI Chatbot Engineer).

Public surface:
    ChatbotService — session/turn orchestrator
    llm            — LLM provider clients (OpenAI-compatible + labelled mock)
    tools          — structured tool schemas + registry
    gateway        — permission-scoped read-only data queries
    identity       — identity verification + signed chat tokens
    prompts        — system prompts and grounded policy text
    models         — chat_session / chat_message persistence
    data_models    — read-only views over the existing application tables
"""

from .service import ChatbotError, ChatbotService  # noqa: F401

__all__ = ["ChatbotService", "ChatbotError"]
