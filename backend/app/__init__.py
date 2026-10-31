"""PaMarket Flask application factory."""
import logging

from flask import Flask, jsonify

from .config import get_config
from .extensions import db, init_extensions
from .errors import register_error_handlers
from .routes import register_blueprints


def create_app(config_name: str | None = None) -> Flask:
    app = Flask("pamarket")
    app.config.from_object(get_config(config_name))

    logging.basicConfig(level=logging.INFO)

    init_extensions(app)
    register_error_handlers(app)
    register_blueprints(app)

    from .models import Base  # noqa: F401  (import registers all tables)
    from .utils.seed import register_seed_command
    register_seed_command(app)

    @app.get("/healthz")
    def healthz():
        db_ok = True
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception:  # pragma: no cover - health endpoint
            db_ok = False
        return (
            jsonify(
                {
                    "service": app.config["APP_NAME"],
                    "status": "ok" if db_ok else "degraded",
                    "database": "connected" if db_ok else "unavailable",
                    "payments": app.config["DEVDRAFT_MODE"],
                    "api": app.config["API_PREFIX"],
                }
            ),
            200 if db_ok else 503,
        )

    return app
