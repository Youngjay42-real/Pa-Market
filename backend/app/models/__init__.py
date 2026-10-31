"""All PaMarket SQLAlchemy models — import to register tables with the metadata."""
from .base import Base
from .user import User
from .vendor import Vendor
from .stand import Stand
from .application import Application
from .allocation import Allocation, permit_code
from .handover import HandoverConfirmation
from .payment import Payment, PaymentEvent
from .notification import Notification
from .audit_log import AuditLog, CorruptionReport

__all__ = [
    "Base",
    "User",
    "Vendor",
    "Stand",
    "Application",
    "Allocation",
    "permit_code",
    "HandoverConfirmation",
    "Payment",
    "PaymentEvent",
    "Notification",
    "AuditLog",
    "CorruptionReport",
]

# NOTE: chat persistence (chat_session / chat_message) is owned by the Market
# Assistant package (app/chatbot/models.py). Those two tables are created
# idempotently by the chatbot service at startup and are intentionally not part
# of the Alembic chain — see docs/DATABASE_SCHEMA.md.
