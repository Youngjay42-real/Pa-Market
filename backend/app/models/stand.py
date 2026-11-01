"""Physical market stands with grid coordinates (mirrors the interactive map)."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Stand(Base):
    __tablename__ = "stands"

    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)  # e.g. ST-001
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    col: Mapped[int] = mapped_column(Integer, nullable=False)
    zone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="available", nullable=False, index=True)
    vendor_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    vendor_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    vendor_nrc: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    allocated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hold_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("5.00"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ZMW")

    vendor = relationship("Vendor", foreign_keys=[vendor_id], backref="stands")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Stand {self.code} {self.zone} {self.status}>"
