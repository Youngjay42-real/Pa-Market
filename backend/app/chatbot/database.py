"""Database plumbing for the chatbot service.

Owns:
- URL normalisation (Prisma-style ``file:`` URLs -> SQLAlchemy URLs)
- Engine / session factory construction
- Idempotent creation of the chatbot-owned tables (``chat_session``, ``chat_message``)

The chatbot service deliberately uses plain SQLAlchemy with its own metadata so it can
be wired into whatever app/extension setup the backend leads builds
(``backend/app/config.py`` + ``extensions.py`` are thin integration points).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

# backend/app/chatbot/database.py -> backend/app/chatbot -> backend/app -> backend -> repo root
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent
_PRISMA_DIR = _REPO_ROOT / "prisma"
_INSTANCE_DIR = _BACKEND_DIR / "instance"

# Development fallback: the same SQLite file the PaMarket Flask app uses by
# default (backend/instance/pa_market_dev.db). In production CHATBOT_DATABASE_URL
# or DATABASE_URL points at Neon PostgreSQL, so the chat tables live in the same
# database as the application tables.
_DEFAULT_SQLITE_PATH = _BACKEND_DIR / "instance" / "pa_market_dev.db"
DEFAULT_SQLITE_URL = f"sqlite:///{_DEFAULT_SQLITE_PATH}"

_SESSION_FACTORY: Optional[sessionmaker] = None


def normalise_url(raw: Optional[str]) -> str:
    """Translate the many accepted forms into a SQLAlchemy engine URL.

    Accepted:
      * ``file:./dev.db``            (Prisma style, resolved against ``prisma/``)
      * ``sqlite:///path``           (standard SQLAlchemy)
      * ``postgresql://...``         (psycopg2 threaded URLs; translated to the
                                      +psycopg dialect so SQLAlchemy can pick the driver)
      * empty/missing               -> the local Prisma SQLite file used by the app
    """
    if not raw:
        return DEFAULT_SQLITE_URL

    url = raw.strip()

    if url.startswith("file:"):
        # Prisma-style files (the Next.js app keeps its own database in prisma/)
        # resolve to explicit candidate paths instead of opaque driver URLs.
        rel = url[len("file:") :].lstrip("./")
        lowered = rel.lower()
        candidates = [
            _INSTANCE_DIR / rel,  # backend instance dir (chatbot default location)
            _BACKEND_DIR / rel,
            _PRISMA_DIR / rel,  # legacy: the Next.js app's prisma database
            _REPO_ROOT / rel,
        ]
        if lowered.startswith("prisma/"):
            trimmed = rel[len("prisma/") :]
            candidates.insert(0, _PRISMA_DIR / trimmed)
        for candidate in candidates:
            if candidate.exists():
                return f"sqlite:///{candidate}"
        # Nothing exists yet: create the file in the backend instance dir.
        return f"sqlite:///{candidates[0]}"

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    if url.startswith("postgresql+psycopg://"):
        # Neon et al. always require TLS; enforce unless the caller already opted out.
        if "sslmode" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"

    return url


def resolve_database_url(env: Optional[Dict[str, str]] = None) -> str:
    env = dict(env or os.environ)
    raw = env.get("CHATBOT_DATABASE_URL")
    if raw:
        return normalise_url(raw)
    shared = (env.get("DATABASE_URL") or "").strip()
    # In production the chatbot shares the app's database (Neon). Prisma-style
    # ``file:`` URLs are ignored on purpose: they belong to the Next.js
    # prototype's own database, never to PaMarket's schema.
    if shared.startswith(("postgresql://", "postgres://", "sqlite://", "sqlite:///")):
        return normalise_url(shared)
    return DEFAULT_SQLITE_URL


def make_engine(url: str, **kwargs: Any) -> Engine:
    engine_kwargs: Dict[str, Any] = {"future": True}
    if url.startswith("sqlite://"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine_kwargs.update(kwargs)
    return create_engine(url, **engine_kwargs)


def configure_database(url: str) -> sessionmaker:
    """Create the engine + session factory and ensure the chat schema exists."""
    global _SESSION_FACTORY
    engine = make_engine(url)

    # Import here to avoid a cycle; models register on the shared metadata.
    from . import models as _models  # noqa: F401  (ensures table defs are loaded)

    _models.Base.metadata.create_all(bind=engine)

    _SESSION_FACTORY = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return _SESSION_FACTORY


def get_session_factory() -> sessionmaker:
    if _SESSION_FACTORY is None:
        configure_database(resolve_database_url())
    return _SESSION_FACTORY  # type: ignore[return-value]


@contextmanager
def session_scope():
    """Provide a transactional scope; commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def healthcheck() -> bool:
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:  # pragma: no cover - surfaced via /health endpoint
        return False
