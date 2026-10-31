"""Environment-driven configuration for the chatbot service.

Developer 3 note: this module is deliberately small. The backend lead (Developer 1)
will grow it into the full backend config alongside their app factory — the chatbot
service only needs the ``CHATBOT_*`` variables documented in
docs/CHATBOT_CONTRACT.md §9.
"""

from __future__ import annotations

import os
from typing import Dict, List

KNOWN_VARS = (
    "CHATBOT_DATABASE_URL",
    "CHATBOT_SECRET_KEY",
    "CHATBOT_LLM_PROVIDER",
    "CHATBOT_LLM_API_KEY",
    "CHATBOT_LLM_MODEL",
    "CHATBOT_LLM_BASE_URL",
    "CHATBOT_CORS_ORIGINS",
    "CHATBOT_PORT",
)


def env() -> Dict[str, str]:
    return {name: os.environ.get(name, "") for name in KNOWN_VARS}


def environment_warnings() -> List[str]:
    warnings: List[str] = []
    if not os.environ.get("CHATBOT_SECRET_KEY"):
        warnings.append(
            "CHATBOT_SECRET_KEY is not set — chat tokens use the development fallback secret. "
            "Set a long random value before any real deployment."
        )
    provider = (os.environ.get("CHATBOT_LLM_PROVIDER") or "mock").lower()
    if provider == "mock":
        warnings.append(
            "CHATBOT_LLM_PROVIDER=mock — the assistant runs the deterministic offline client. "
            "Configure CHATBOT_LLM_PROVIDER/CHATBOT_LLM_API_KEY for real LLM answers."
        )
    return warnings
