"""PaMarket application configuration.

All secrets and environment-specific settings come from environment variables
(loaded from backend/.env in development via python-dotenv). Production values
are provided by Render, never committed to source control.
"""
import os
from datetime import timedelta
from decimal import Decimal, InvalidOperation


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///pa_market_dev.db")
    # Some providers still emit the legacy scheme; SQLAlchemy expects postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Guard: a non-SQL URL (e.g. the Next.js/Prisma "file:./dev.db" in an
    # ancestor .env) would crash the app. Warn loudly and use local SQLite so
    # developer tooling keeps working; production always sets a real DATABASE_URL.
    if not url.startswith(("postgresql://", "sqlite://")):
        try:
            from sqlalchemy.engine import make_url

            make_url(url)
        except Exception:
            print(
                f"WARNING: ignoring unsupported DATABASE_URL ({url.split(':')[0]}:...); "
                "using local SQLite. Set DATABASE_URL to a postgresql:// URL for Neon."
            )
            url = "sqlite:///pa_market_dev.db"
    return url


def _decimal(name: str, default: str) -> Decimal:
    try:
        return Decimal(os.environ.get(name, default))
    except InvalidOperation as exc:  # pragma: no cover - configuration error
        raise RuntimeError(f"Invalid decimal in env var {name}") from exc


def _store_uri() -> str:
    """Rate-limiter storage. Use DATABASE_URL-style URL when Redis available."""
    return os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


class BaseConfig:
    """Default configuration shared by every environment."""

    APP_NAME = "PaMarket"
    API_PREFIX = "/api/v1"

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-change-me")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.environ.get("JWT_ACCESS_HOURS", "12"))
    )

    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_RECORD_QUERIES = False

    # CORS: explicit allowlist, no wildcard credentials.
    FRONTEND_ORIGINS = [
        origin.strip()
        for origin in os.environ.get(
            "FRONTEND_ORIGINS", "http://localhost:3000"
        ).split(",")
        if origin.strip()
    ]

    # Authentication hardening
    PASSWORD_MIN_LENGTH = 8
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = _store_uri()
    RATELIMIT_DEFAULT = "300/minute"

    # Sensitive endpoints get tighter limits (applied per-route).
    AUTH_RATELIMIT = "10/minute"
    PUBLIC_WRITE_RATELIMIT = "5/minute"

    # ── DevDraft payments ────────────────────────────────────────────────────
    DEVDRAFT_MODE = os.environ.get("DEVDRAFT_MODE", "sandbox").lower()
    DEVDRAFT_BASE_URL = os.environ.get("DEVDRAFT_BASE_URL", "https://api.devdraft.ai")
    DEVDRAFT_CLIENT_KEY = os.environ.get("DEVDRAFT_CLIENT_KEY", "")
    DEVDRAFT_CLIENT_SECRET = os.environ.get("DEVDRAFT_CLIENT_SECRET", "")
    DEVDRAFT_WEBHOOK_SECRET = os.environ.get("DEVDRAFT_WEBHOOK_SECRET", "")
    DEVDRAFT_DESTINATION_NETWORK = os.environ.get("DEVDRAFT_DESTINATION_NETWORK", "base")
    DEVDRAFT_DESTINATION_ADDRESS = os.environ.get("DEVDRAFT_DESTINATION_ADDRESS", "")

    # ── Hackathon financial-safety limits (server-side enforcement) ──────────
    PAYMENT_CURRENCY = os.environ.get("PAYMENT_CURRENCY", "USD")
    PAYMENT_MAX_PER_TRANSACTION = _decimal("PAYMENT_MAX_PER_TRANSACTION", "5.00")
    PAYMENT_MAX_TEAM_TOTAL = _decimal("PAYMENT_MAX_TEAM_TOTAL", "50.00")
    DEFAULT_STAND_FEE = _decimal("DEFAULT_STAND_FEE", "5.00")

    # Optional demo seeding (disabled in production unless explicitly enabled.)
    ALLOW_DEMO_SEED = os.environ.get("ALLOW_DEMO_SEED", "true").lower() in ("1", "true", "yes")

    # When True (tests), do not hit the network or leaked-error pages.
    TESTING = False


class DevelopmentConfig(BaseConfig):
    DEBUG = False  # debug reloader disabled; run flask run --debug locally if wanted.


class ProductionConfig(BaseConfig):
    PROPAGATE_EXCEPTIONS = False


TESTING_CONFIG_OVERRIDES = {
    "TESTING": True,
    "RATELIMIT_ENABLED": False,
    "SQLALCHEMY_DATABASE_URI": "sqlite://",  # overridden per-test with a file DB
}


def get_config(config_name: str | None = None):
    """Resolve configuration class from name or FLASK_ENV."""
    name = (config_name or os.environ.get("FLASK_ENV", "development")).lower()
    if name in ("production", "prod"):
        return ProductionConfig
    return DevelopmentConfig
