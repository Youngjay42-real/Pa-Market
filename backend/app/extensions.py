"""Shared Flask extension instances (created once, bound in create_app)."""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address)


def get_chatbot_service():
    """Process-wide Market Assistant service (lazily built from env config).

    Kept in this module so routes/tests can inject deterministic clients with
    ``set_chatbot_service``; the chatbot package itself stays decoupled from the
    Flask app wiring.
    """
    global _chatbot_service
    if _chatbot_service is None:
        from .chatbot import ChatbotService

        _chatbot_service = ChatbotService()
    return _chatbot_service


_chatbot_service = None


def set_chatbot_service(service) -> None:
    """Test/factory hook: inject (or clear) a ChatbotService instance."""
    global _chatbot_service
    _chatbot_service = service


def init_extensions(app) -> None:
    """Attach every extension to the application instance."""
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGINS"]}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        max_age=600,
    )
    limiter.init_app(app)
