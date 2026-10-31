"""PaMarket domain constants.

Zone and business-category values mirror the existing frontend
(`src/constants/businessCategories.ts`) so both applications stay in sync.
"""
from enum import StrEnum

MARKET_ZONES = ("Produce", "Textiles", "Hardware", "Food Court")

BUSINESS_CATEGORIES = (
    "Food & Fresh Produce",
    "Electronics & Gadgets",
    "Clothing & Apparel",
    "Hardware & Tools",
    "Beauty & Cosmetics",
    "Handicrafts & Curios",
    "Tailoring & Textiles",
    "Footwear & Leather",
    "Livestock & Poultry",
    "Stationery & Books",
    "General Merchandise",
    "Services & Repairs",
)

BUSINESS_CATEGORY_ZONES = {
    "Food & Fresh Produce": ("Produce", "Food Court"),
    "Electronics & Gadgets": ("Hardware",),
    "Clothing & Apparel": ("Textiles",),
    "Hardware & Tools": ("Hardware",),
    "Beauty & Cosmetics": ("Textiles", "Food Court"),
    "Handicrafts & Curios": ("Textiles", "Produce"),
    "Tailoring & Textiles": ("Textiles",),
    "Footwear & Leather": ("Textiles",),
    "Livestock & Poultry": ("Produce",),
    "Stationery & Books": ("Hardware", "Food Court"),
    "General Merchandise": MARKET_ZONES,
    "Services & Repairs": ("Hardware", "Food Court"),
}


def zones_for_category(business_type: str | None) -> tuple[str, ...]:
    if not business_type:
        return MARKET_ZONES
    return BUSINESS_CATEGORY_ZONES.get(business_type, MARKET_ZONES)


class Role(StrEnum):
    VENDOR = "vendor"
    ADMIN = "admin"


class StandStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"


class ApplicationStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    ALLOCATED = "allocated"  # a stand allocation was created from this application
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class AllocationStatus(StrEnum):
    OFFERED = "offered"                       # admin offered a stand, awaiting vendor acceptance
    ACCEPTED = "accepted"                     # vendor accepted, awaiting handover
    HANDOVER_CONFIRMED = "handover_confirmed" # both vendor and official confirmed
    COMPLETED = "completed"                   # payment succeeded, permit issued
    CANCELLED = "cancelled"
    EXPIRED = "expired"                       # vendor never accepted the offer


class HandoverRole(StrEnum):
    VENDOR = "vendor"
    OFFICIAL = "official"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class NotificationType(StrEnum):
    APPLICATION_RECEIVED = "application_received"
    APPLICATION_APPROVED = "application_approved"
    APPLICATION_REJECTED = "application_rejected"
    ALLOCATION_OFFERED = "allocation_offered"
    ALLOCATION_ACCEPTED = "allocation_accepted"
    HANDOVER_CONFIRMED = "handover_confirmed"
    PAYMENT_SUCCESSFUL = "payment_successful"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_REFUNDED = "payment_refunded"
    REPORT_RECEIVED = "report_received"
