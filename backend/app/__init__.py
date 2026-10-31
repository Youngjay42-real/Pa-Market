"""StandProof Flask application factory — minimal additive foundation.

NOTE (Developer 3): the full backend (auth, payments, allocations) belongs to
Developer 1 (backend lead). This factory is intentionally small — just enough to
run the chatbot service standalone (wsgi.py) and expose the documented REST
endpoints. When the backend lead's own factory lands, merge this blueprint:

    from .routes.chatbot import blueprint as chatbot_blueprint
    app.register_blueprint(chatbot_blueprint)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from flask import Flask, jsonify, request

from .config import environment_warnings
from .chatbot.database import configure_database, resolve_database_url
from .routes.chatbot import blueprint as chatbot_blueprint

log = logging.getLogger("standproof")

ASSISTANT_NAME = "StandProof Market Assistant"


def _allowed_origins(app: Flask) -> list[str]:
    raw = app.config.get("CHATBOT_CORS_ORIGINS") or os.environ.get("CHATBOT_CORS_ORIGINS") or "http://localhost:3000"
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def create_app() -> Flask:
    app = Flask("standproof_backend")
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # small JSON payloads only

    # Single-process threaded behaviour suits the chatbot's blocking LLM calls
    # until a proper WSGI setup (Gunicorn + Gevent) is chosen by the backend lead.
    app.config["CHATBOT_CORS_ORIGINS"] = os.environ.get("CHATBOT_CORS_ORIGINS")

    configure_database(resolve_database_url())

    for warning in environment_warnings():
        log.warning(warning)

    app.register_blueprint(chatbot_blueprint)

    # ------------------------------------------------------------------
    # root + shared health endpoints (public)
    # ------------------------------------------------------------------

    @app.get("/")
    def root():
        return jsonify(
            {
                "service": "standproof-backend",
                "assistant": ASSISTANT_NAME,
                "api": "/api/v1/chatbot",
                "docs": "/docs/CHATBOT_CONTRACT.md",
            }
        )

    @app.get("/healthz")
    @app.get("/api/v1/health")
    def service_health():
        return jsonify({"status": "ok", "service": "standproof-backend"})

    # ------------------------------------------------------------------
    # CORS — dependency-free, restricted to configured widget origins
    # ------------------------------------------------------------------

    @app.after_request
    def apply_cors(response):
        origin = request.headers.get("Origin")
        if origin and origin in _allowed_origins(app):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Vary"] = "Origin"
        if request.method == "OPTIONS":
            response.status_code = 204
        return response

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify({"error": {"code": "invalid_request", "message": "Method not allowed."}}), 405

    @app.errorhandler(Exception)
    def unhandled(error: Exception):
        # Never leak stack traces or internals (master prompt §10).
        log.exception("Unhandled error: %s", type(error).__name__)
        return jsonify({"error": {"code": "internal_error", "message": "Something went wrong. Please try again."}}), 500

    return app


def reset_database_cache() -> None:
    """Test helper — clears the cached engine/session factory (chatbot/database.py)."""
    from .chatbot import database as chatbot_db

    chatbot_db._SESSION_FACTORY = None


__all__ = ["create_app", "reset_database_cache"]
