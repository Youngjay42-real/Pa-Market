"""Chatbot-owned persistence: chat sessions and chat messages.

These two tables are part of Developer 3's domain. They are intentionally separate
from the application tables (which belong to the backend lead) and are created
idempotently at service startup. When the backend lead's Alembic chain lands, these
table definitions should be lifted into ``backend/migrations`` — see the hardening
roadmap in docs/CHATBOT_CONTRACT.md §12.

The tables use snake_case + the ``chat_`` prefix so they can co-exist with the
Prisma-generated tables (which use mixed-case names like ``User``, ``Stand``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_session_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    """Shared declarative base for chatbot-owned tables only."""


class ChatSession(Base):
    __tablename__ = "chat_session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_session_id)

    # Identity snapshot bound at creation time. For guest sessions the *_id fields
    # hold a random visitor id and kind == "guest".
    kind: Mapped[str] = mapped_column(String(16), default="guest")  # guest | verified
    user_id: Mapped[str] = mapped_column(String(64), default="")
    user_name: Mapped[str] = mapped_column(String(160), default="")
    user_phone: Mapped[str] = mapped_column(String(32), default="")
    user_role: Mapped[str] = mapped_column(String(16), default="guest")  # guest | vendor | admin
    user_nrc: Mapped[str] = mapped_column(String(64), default="")
    user_business_type: Mapped[str] = mapped_column(String(120), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)

    messages: Mapped[list["ChatMessage"]] = relationship(  # noqa: F821
        "ChatMessage", lazy="dynamic", cascade="all, delete-orphan"
    )

    def as_public_dict(self) -> dict:
        return {
            "sessionId": self.id,
            "kind": self.kind,
            "role": self.user_role,
            "displayName": self.user_name or "Guest",
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "messageCount": self.message_count,
            "closed": self.closed,
        }


class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("chat_session.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(12))  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tool_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    degraded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def as_client_dict(self, include_tool_meta: bool = False) -> dict:
        payload = {
            "id": str(self.id),
            "role": self.role,
            "content": self.content,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
        if self.role == "assistant":
            payload["meta"] = {
                "verified": bool(self.verified),
                "toolsUsed": (self.tool_name or "").split(",") if self.tool_name else [],
                "degraded": bool(self.degraded),
            }
        elif include_tool_meta and self.role == "tool":
            payload.update({"tool": self.tool_name, "payload": self.tool_payload})
        return payload
