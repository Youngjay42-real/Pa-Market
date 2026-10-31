"""Backend-side input validation (never trust the browser)."""
import re
from datetime import datetime, timezone

from ..constants import BUSINESS_CATEGORIES, MARKET_ZONES
from ..errors import ApiError

NRC_RE = re.compile(r"^\d{5,7}[/-]\d{1,2}[/-]\d{1,2}$")  # e.g. 123456/78/1
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{6,19}$")


def require(body: dict | None, *fields: str) -> dict:
    if not isinstance(body, dict):
        raise ApiError(400, "invalid_json", "Request body must be a JSON object.")
    missing = [f for f in fields if not body.get(f)]
    if missing:
        raise ApiError(400, "missing_fields", "Missing required fields.", {"fields": missing})
    return body


def normalize_phone(raw: str) -> str:
    if not isinstance(raw, str) or not _PHONE_RE.match(raw.strip()):
        raise ApiError(400, "invalid_phone", "Provide a valid phone number (e.g. 0977123456).")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("260"):
        digits = "0" + digits[3:]
    if not digits.startswith("0"):
        digits = "0" + digits
    if len(digits) < 9 or len(digits) > 13:
        raise ApiError(400, "invalid_phone", "Phone number length is invalid.")
    return digits


def normalize_nrc(raw: str) -> str:
    value = (raw or "").strip().upper()
    if not NRC_RE.match(value):
        raise ApiError(400, "invalid_nrc", "NRC must look like 123456/78/1.")
    return value.replace("-", "/")


def business_type(raw: str | None) -> str:
    value = (raw or "General Merchandise").strip()
    if value not in BUSINESS_CATEGORIES:
        raise ApiError(
            400, "invalid_business_type", "Unknown business category.",
            {"allowed": list(BUSINESS_CATEGORIES)},
        )
    return value


def preferred_zone(raw: str | None) -> str | None:
    value = (raw or "").strip() or None
    if value is not None and value not in MARKET_ZONES:
        raise ApiError(400, "invalid_zone", "Unknown market zone.", {"allowed": list(MARKET_ZONES)})
    return value


def clean_text(raw, max_length: int, field: str) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if len(value) > max_length:
        raise ApiError(400, "field_too_long", f"{field} must be at most {max_length} characters.")
    return value


def parse_decimal(raw, field: str = "amount") -> "decimal.Decimal":
    from decimal import Decimal, InvalidOperation

    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ApiError(400, "invalid_amount", f"{field} must be a decimal number.")
    if value <= 0:
        raise ApiError(400, "invalid_amount", f"{field} must be positive.")
    return value


def password_strength(raw: str) -> str:
    if not isinstance(raw, str) or len(raw) < 8:
        raise ApiError(400, "weak_password", "Password must be at least 8 characters.")
    return raw


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
