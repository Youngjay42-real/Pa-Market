"""Vendor records: queue membership + stand application status per vendor."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow


class Vendor(Base):
    __tablename__ = "vendors"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    nrc: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    business_type: Mapped[str] = mapped_column(String(64), default="General Merchandise", nullable=False)
    preferred_zone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # mtn | airtel | zamtel
    queue_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", backref="vendor", uselist=False)
    applications = relationship(
        "Application",
        back_populates="vendor",
        cascade="all, delete-orphan",
        order_by="Application.created_at.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Vendor {self.nrc} status={self.status}>"
