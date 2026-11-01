"""Payments and their immutable provider event trail (DevDraft integration).

Money columns use Numeric/Decimal — never floating point.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, new_uuid, utcnow

# JSONB where available (Neon), plain JSON elsewhere (tests on SQLite).
JsonType = JSON().with_variant(JSONB(), "postgresql")


def _receipt_number() -> str:
    stamp = utcnow().strftime("%Y%m%d")
    return f"PAM-{stamp}-{new_uuid().hex[:8].upper()}"


class Payment(Base):
    __tablename__ = "payments"

    allocation_id: Mapped[str] = mapped_column(
        ForeignKey("allocations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ZMW")
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False, default="devdraft")
    provider_reference: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    provider_status_raw: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    receipt_no: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    receipt_issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    allocation = relationship("Allocation", back_populates="payments")
    vendor = relationship("Vendor", backref="payments")
    events = relationship(
        "PaymentEvent",
        back_populates="payment",
        cascade="all, delete-orphan",
        order_by="PaymentEvent.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment {self.id} {self.status} {self.amount}>"


class PaymentEvent(Base):
    """Append-only trail: every provider call/webhook delivery lands here."""

    __tablename__ = "payment_events"

    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "provider_provider_status_changed" | "webhook_received" | "sync" | "refund" ...
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    provider_event_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    raw_status: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JsonType, nullable=True)
    signature_valid: Mapped[Optional[bool]] = mapped_column(nullable=True)

    payment = relationship("Payment", back_populates="events")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PaymentEvent {self.payment_id} {self.event_type}>"
