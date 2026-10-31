"""Read-only rebindings of the PaMarket application tables.

The chatbot only ever SELECTs through these models; they exist so the assistant's
answers stay grounded in the backend lead's canonical SQLAlchemy schema
(`backend/app/models/`) with its Alembic migrations.

Integration note (backend lead): this file is the single seam between the
chatbot package and the application schema. Everything the assistant can read
lives here; `gateway.py` contains every query. Tables that existed in the
original Next.js/Prisma prototype (``DailySale``, ``TaxPayment``,
``VillageBankingAccount``) have no counterpart in PaMarket and were dropped —
``get_my_financials`` now derives a stand-levy summary from ``payments`` /
``allocations`` instead of touching those legacy tables.
"""

from __future__ import annotations

# Re-export the CANONICAL ORM models (read-only by convention; the chatbot never
# adds/edits rows through them). Query code uses them with ``select()``.
from ..models import (  # noqa: F401
    Application,
    AuditLog,
    Allocation,
    CorruptionReport as Report,
    Notification,
    Payment,
    Stand,
    User,
    Vendor,
)

__all__ = [
    "Application",
    "Allocation",
    "AuditLog",
    "Notification",
    "Payment",
    "Report",
    "Stand",
    "User",
    "Vendor",
]
