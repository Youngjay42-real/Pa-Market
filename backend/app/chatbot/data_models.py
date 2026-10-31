"""Read-only table views over the existing application tables.

These maps describe the tables the current Next.js/Prisma implementation creates
(prisma/schema.prisma). The chatbot only ever SELECTs through them; they exist
because these rows feed the assistant's grounded answers about applications,
allocations, payments and audit history.

Developer 1 (backend lead) will introduce the canonical SQLAlchemy models with
proper Alembic migrations on Neon PostgreSQL. When that happens:
  * update the table/column identifiers here only if names change, or
  * swap ``gateway.py`` to use the backend lead's service functions.
Nothing else in the chatbot needs to change — every query lives in ``gateway.py``.

Column names follow the Prisma schema exactly (camelCase identifiers, which Prisma
quotes as-is on both SQLite and PostgreSQL).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

# Dedicated metadata so these views never share declarative state with the chat tables.
legacy_metadata = MetaData()

User = Table(
    "User",
    legacy_metadata,
    Column("id", String(64), primary_key=True),
    Column("phone", String(32)),
    Column("fullName", String(160)),
    Column("password", String(255)),  # never selected by gateway queries
    Column("role", String(16)),
    Column("nrc", String(64)),
    Column("businessType", String(120)),
    Column("createdAt", String(64)),
)

Stand = Table(
    "Stand",
    legacy_metadata,
    Column("id", String(64), primary_key=True),
    Column("row", Integer),
    Column("col", Integer),
    Column("zone", String(80)),
    Column("status", String(32)),  # available | occupied | reserved | maintenance
    Column("vendorName", String(160)),
    Column("vendorNrc", String(64)),
    Column("allocatedAt", String(64)),
    Column("holdExpiresAt", String(64)),
)

Vendor = Table(
    "Vendor",
    legacy_metadata,
    Column("nrc", String(64), primary_key=True),
    Column("fullName", String(160)),
    Column("phone", String(32)),
    Column("queuePosition", Integer),
    Column("status", String(32)),  # pending | allocated | rejected
    Column("standId", String(64)),
    Column("businessType", String(120)),
    Column("preferredZone", String(80)),
    Column("paymentMethod", String(64)),
    Column("appliedAt", String(64)),
)

Payment = Table(
    "Payment",
    legacy_metadata,
    Column("id", String(64), primary_key=True),
    Column("vendorNrc", String(64)),
    Column("amount", Float),
    Column("currency", String(8)),
    Column("status", String(32)),  # pending | confirmed | failed
    Column("method", String(64)),
    Column("receiptNo", String(64)),
    Column("createdAt", String(64)),
)

Notification = Table(
    "Notification",
    legacy_metadata,
    Column("id", String(64), primary_key=True),
    Column("vendorNrc", String(64)),
    Column("type", String(64)),
    Column("title", String(160)),
    Column("message", Text),
    Column("receiptJson", Text),
    Column("read", Boolean),
    Column("createdAt", String(64)),
)

AuditLog = Table(
    "AuditLog",
    legacy_metadata,
    Column("id", String(64), primary_key=True),
    Column("action", String(120)),
    Column("actor", String(160)),
    Column("entityType", String(64)),
    Column("entityId", String(64)),
    Column("details", Text),
    Column("timestamp", String(64)),
)

Report = Table(
    "Report",
    legacy_metadata,
    Column("id", String(64), primary_key=True),
    Column("category", String(80)),
    Column("description", Text),
    Column("location", String(160)),
    Column("contactEmail", String(160)),
    Column("createdAt", String(64)),
)

DailySale = Table(
    "DailySale",
    legacy_metadata,
    Column("id", String(64), primary_key=True),
    Column("vendorNrc", String(64)),
    Column("amount", Float),
    Column("taxAmount", Float),
    Column("date", String(64)),
    Column("status", String(16)),  # unpaid | paid
)

TaxPayment = Table(
    "TaxPayment",
    legacy_metadata,
    Column("id", String(64), primary_key=True),
    Column("vendorNrc", String(64)),
    Column("amount", Float),
    Column("paidAt", String(64)),
    Column("receiptNo", String(64)),
)

VillageBankingAccount = Table(
    "VillageBankingAccount",
    legacy_metadata,
    Column("id", String(64), primary_key=True),
    Column("vendorNrc", String(64)),
    Column("groupId", String(64)),
    Column("balance", Float),
    Column("savingsGoal", Float),
    Column("interestRate", Float),
    Column("createdAt", String(64)),
)
