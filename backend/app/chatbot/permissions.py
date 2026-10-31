"""Role-based capability checking for chatbot tools.

Every tool executes against an :class:`AccessContext`. Vendor tools are bound to
the context's own nrc/phone — there is no code path that lets a caller pass
another vendor's identifiers, which is what prevents cross-vendor data exposure
(CHATBOT_CONTRACT.md §1 guarantee 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from .identity import Identity


@dataclass(frozen=True)
class AccessContext:
    identity: Identity
    session: Session

    @property
    def vendor_key(self) -> str:
        """The NRC this context may access — empty for non-vendors."""
        return self.identity.nrc or ""

    @property
    def phone(self) -> str:
        return self.identity.phone


class PermissionDenied(Exception):
    """Raised inside tools; converted to a structured denial for the LLM."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def require_verified(ctx: AccessContext) -> None:
    if not ctx.identity.is_verified:
        raise PermissionDenied(
            "This information is private. Log in with your vendor account so I can look up your own records."
        )


def require_vendor(ctx: AccessContext) -> str:
    """Guarantee a verified vendor context; returns the vendor NRC to scope by."""
    require_verified(ctx)
    if not ctx.identity.is_vendor:
        raise PermissionDenied("This information is only available to vendor accounts.")
    if not ctx.vendor_key:
        raise PermissionDenied(
            "Your account has no NRC on file, so personal records cannot be looked up."
        )
    return ctx.vendor_key


def require_admin(ctx: AccessContext) -> None:
    require_verified(ctx)
    if not ctx.identity.is_admin:
        raise PermissionDenied(
            "This market-wide information is only available to authorised council administrators."
        )


def denial(message: str) -> dict:
    """The structured payload the LLM receives when a tool refuses."""
    return {
        "ok": False,
        "denied": True,
        "error": message,
        "hint": "Explain the limitation politely and suggest what the user can do instead.",
    }
