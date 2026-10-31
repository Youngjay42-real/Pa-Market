"""Tamper-evident audit trail (hash-chained, append-only by convention)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)          # user id or "system"
    actor_role: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    details: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.action} {self.entity_type}={self.entity_id}>"


class CorruptionReport(Base):
    """Whistleblower submissions (public endpoint, pseudonymous ok)."""

    __tablename__ = "corruption_reports"

    reference: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="received", nullable=False, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CorruptionReport {self.reference} {self.category}>"
