"""Vendor stand applications flowing through the council review queue."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Application(Base):
    __tablename__ = "applications"

    vendor_id: Mapped[str] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stand_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("stands.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="submitted", nullable=False, index=True)
    queue_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    business_type: Mapped[str] = mapped_column(String(64), nullable=False)
    preferred_zone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    vendor = relationship("Vendor", back_populates="applications")  # many applications per vendor is allowed

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Application {self.id} {self.status}>"
