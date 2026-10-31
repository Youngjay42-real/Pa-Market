"""Model base classes and helpers shared by every table."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


def new_uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(db.Model):
    """Common columns for all models."""

    __abstract__ = True

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=new_uuid
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    def __init__(self, **kwargs):
        # Pre-generate the id so services can reference it before flush
        # (audit entries and notification payloads need it immediately).
        if "id" not in kwargs:
            kwargs["id"] = new_uuid()
        super().__init__(**kwargs)

    def to_dict(self) -> dict:  # pragma: no cover - debug helper
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
