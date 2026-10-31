"""Identity verification + signed chat tokens.

The chatbot never asks users for their password inside the chat. A *verified*
session requires the client to present the profile of the app session
(``app_user``): phone, full name, role and (when present) NRC. The service checks
that this profile matches exactly ONE User row before issuing a signed chat token
that binds that identity for 24 hours.

See docs/CHATBOT_CONTRACT.md §3 (identity model) and §12 (hardening roadmap —
this module is the seam to replace with the backend lead's JWT provider).
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select

from .data_models import User

TOKEN_SALT = "standproof-chat-v1"
TOKEN_TTL_SECONDS = 24 * 3600

DEV_FALLBACK_SECRET = "standproof-dev-secret-do-not-use-in-production"

ALLOWED_ROLES = ("vendor", "admin")


@dataclass(frozen=True)
class Identity:
    """An identity attached to a chat session."""

    kind: str = "guest"  # guest | verified
    user_id: str = ""
    full_name: str = ""
    phone: str = ""
    role: str = "guest"  # guest | vendor | admin
    nrc: str = ""  # vendors only
    business_type: str = ""  # vendors only

    @property
    def is_verified(self) -> bool:
        return self.kind == "verified"

    @property
    def is_admin(self) -> bool:
        return self.is_verified and self.role == "admin"

    @property
    def is_vendor(self) -> bool:
        return self.is_verified and self.role == "vendor"

    @property
    def display_name(self) -> str:
        return self.full_name or "Guest"

    def token_payload(self) -> Dict[str, Any]:
        return {
            "sub": self.user_id,
            "kind": self.kind,
            "name": self.full_name,
            "phone": self.phone,
            "role": self.role,
            "nrc": self.nrc,
            "biz": self.business_type,
        }

    def public_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "role": self.role if self.is_verified else "guest",
            "displayName": self.display_name,
        }


GUEST = Identity()


def guest_id() -> Identity:
    """A fresh untracked guest identity (unique per session)."""
    return replace(GUEST, kind="guest", user_id=f"guest-{os.urandom(8).hex()}")


def secret_key() -> str:
    return os.environ.get("CHATBOT_SECRET_KEY", DEV_FALLBACK_SECRET)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_identity_payload(payload: Optional[Dict[str, Any]]) -> Identity:
    """Parse what the widget presented. Returns an Identity WITHOUT verification."""
    if not payload:
        return guest_id()

    phone = _clean(payload.get("phone"))
    full_name = _clean(payload.get("fullName"))
    role = _clean(payload.get("role")).lower() or "vendor"

    if not phone or not full_name:
        # half-supplied profiles are treated as guests (never as verification attempts)
        return guest_id()

    return Identity(
        kind="verified",
        user_id=_clean(payload.get("id")) or "unverified",
        full_name=full_name,
        phone=phone,
        role=role if role in ALLOWED_ROLES else "vendor",
        nrc=_clean(payload.get("nrc")),
        business_type=_clean(payload.get("businessType")),
    )


def _matches(left: str, right: str) -> bool:
    """Timing-safe equality on normalised text (case/space-insensitive)."""
    left = " ".join(left.lower().split())
    right = " ".join(right.lower().split())
    return hmac.compare_digest(left, right)


def verify_identity(session, payload: Optional[Dict[str, Any]]) -> Tuple[Optional[Identity], Optional[str]]:
    """Verify the presented profile against the User table.

    Returns ``(identity, error)`` where error is a stable, non-enumerating string.
    Deliberately does NOT touch passwords — the widget never receives them
    ( CONTRACT §3 ). Role/NRC/name must all agree with one stored row.
    """
    parsed = parse_identity_payload(payload)
    if not parsed.is_verified:
        return parsed, None  # guest creation always succeeds

    rows = [dict(row._mapping) for row in session.execute(select(User).where(User.c.phone == parsed.phone)).all()]
    if not rows:
        return None, "identity_invalid"

    match: Optional[dict] = None
    for user in rows:
        name_ok = _matches(user.get("fullName") or "", parsed.full_name)
        role_ok = _matches((user.get("role") or "vendor").lower(), parsed.role)
        stored_nrc = (user.get("nrc") or "").strip()
        if stored_nrc:
            nrc_ok = _matches(stored_nrc, parsed.nrc)
        else:
            # users with no NRC (e.g. admins) must not present one
            nrc_ok = parsed.nrc == ""
        if name_ok and role_ok and nrc_ok:
            match = user
            break

    if match is None:
        return None, "identity_invalid"

    verified = Identity(
        kind="verified",
        user_id=match.get("id") or "",
        full_name=match.get("fullName") or parsed.full_name,
        phone=match.get("phone") or "",
        role=(match.get("role") or "vendor").lower(),
        nrc=(match.get("nrc") or "").strip(),
        business_type=(match.get("businessType") or parsed.business_type or "").strip(),
    )
    return verified, None


# --------------------------------------------------------------------------
# Signed chat tokens (itsdangerous) — single-purpose, short-lived, chatbot scope
# --------------------------------------------------------------------------

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key(), salt=TOKEN_SALT)


def issue_chat_token(identity: Identity) -> str:
    payload = identity.token_payload()
    return _serializer().dumps(payload)


def read_chat_token(token: str) -> Optional[Identity]:
    """Validate a chat token; returns the embedded Identity or None."""
    if not token:
        return None
    try:
        payload = _serializer().loads(token, max_age=TOKEN_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or "sub" not in payload:
        return None
    kind = payload.get("kind", "guest")
    role = payload.get("role", "guest")
    if kind not in ("guest", "verified") or role not in ("guest",) + ALLOWED_ROLES:
        return None
    return Identity(
        kind=kind,
        user_id=str(payload.get("sub", "")),
        full_name=str(payload.get("name", "")),
        phone=str(payload.get("phone", "")),
        role=role,
        nrc=str(payload.get("nrc", "")),
        business_type=str(payload.get("biz", "")),
    )


def token_ttl() -> timedelta:
    return timedelta(seconds=TOKEN_TTL_SECONDS)
