"""Handover confirmations: vendor + council official both must confirm."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class HandoverConfirmation(Base):
    __tablename__ = "handover_confirmations"
    __table_args__ = (
        UniqueConstraint("allocation_id", "role", name="uq_handover_allocation_role"),
    )

    allocation_id: Mapped[str] = mapped_column(
        ForeignKey("allocations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "vendor" | "official" — one confirmation from each side is required.
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    confirmed_by: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meeting_location: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    allocation = relationship("Allocation", back_populates="confirmations")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HandoverConfirmation {self.allocation_id} by {self.role}>"
