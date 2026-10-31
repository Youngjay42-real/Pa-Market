"""Stand allocations linking an approved application to a reserved stand."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, new_uuid


def permit_code() -> str:
    return "PAM-PERMIT-" + new_uuid()[:12].upper()


class Allocation(Base):
    __tablename__ = "allocations"

    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stand_id: Mapped[str] = mapped_column(
        ForeignKey("stands.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    vendor_id: Mapped[str] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="offered", nullable=False, index=True)
    offered_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    offer_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("5.00"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    permit_code: Mapped[Optional[str]] = mapped_column(String(40), unique=True, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    application = relationship("Application", backref="allocations", uselist=False)
    stand = relationship("Stand", backref="allocations")
    vendor = relationship("Vendor", backref="allocations")
    confirmations = relationship(
        "HandoverConfirmation",
        back_populates="allocation",
        cascade="all, delete-orphan",
    )
    payments = relationship("Payment", back_populates="allocation")

    def confirmation_by(self, role: str) -> Optional["HandoverConfirmation"]:
        return next((c for c in self.confirmations if c.role == role), None)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Allocation {self.id} {self.status}>"
