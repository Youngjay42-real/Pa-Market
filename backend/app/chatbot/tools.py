"""Chatbot tool registry — structured function calling.

Each tool pairs a JSON-Schema description (what the LLM sees) with a Python
implementation (what actually touches data, via ``gateway``). The service executes
tools after binding them to the session's identity; denial text is fed back to the
LLM so it can explain the boundary (see permissions.denial).

The schemas use the OpenAI-compatible ``{"type": "function", "function": {...}}``
format (CHATBOT_CONTRACT.md §6).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import gateway
from .permissions import AccessContext, PermissionDenied, denial

# --------------------------------------------------------------------------
# JSON Schemas (OpenAI function-calling format)
# --------------------------------------------------------------------------

POLICY_TOPICS = ("allocation", "payments", "permits", "verification", "reports")


def _fn(name: str, description: str, parameters: dict | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters
            or {"type": "object", "properties": {}, "required": []},
        },
    }


TOOL_SCHEMAS: List[dict] = [    _fn(
        "get_market_overview",
        "Verified counts of stands by zone and status, application totals and current queue depth. "
        "Use for questions like 'how many stands are available' or 'how busy is the allocation queue'.",
    ),
    _fn(
        "explain_market_policy",
        "Explain how the market works: stand allocation, application requirements, payments, "
        "digital permits, verification, or how to report problems. Grounded in official policy text.",
        {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": list(POLICY_TOPICS),
                    "description": "The policy area to explain.",
                }
            },
            "required": ["topic"],
        },
    ),
    _fn(
        "get_my_application_status",
        "Verified view of the logged-in vendor's own stand application: status, queue position, "
        "business type, preferred zone, application date, and the allocated stand if any.",
    ),
    _fn(
        "get_my_payments",
        "Verified payment records belonging to the logged-in vendor: amounts, statuses, methods "
        "and receipt numbers. Never exposes other vendors' payments.",
    ),
    _fn(
        "get_my_notifications",
        "Verified notifications for the logged-in vendor, unread count plus the ten latest items.",
    ),
    _fn(
        "get_my_financials",
        "Verified stand-levy financial summary for the logged-in vendor: levy totals paid, "
        "awaiting verification, refunded or disputed, and the fee attached to their active "
        "stand allocation. Derived only from their own payment records.",
    ),
    _fn(
        "get_application_statistics",
        "ADMIN ONLY. Market-wide application statistics, business-type mix, stand occupancy and "
        "payment status totals.",
    ),
    _fn(
        "get_queue_summary",
        "ADMIN ONLY. Pending applications in queue order with preferred zones so the council "
        "team can plan allocations.",
    ),
    _fn(
        "list_recent_allocations",
        "ADMIN ONLY. The most recent stand allocations from the immutable audit log: stand, "
        "vendor, timestamp and allocating officer.",
    ),
    _fn(
        "list_pending_verifications",
        "ADMIN ONLY. Payments awaiting confirmation (with waiting times) and recent corruption "
        "reports that need review.",
    ),
    _fn(
        "find_suspicious_activity",
        "ADMIN ONLY. Rule-based integrity flags: duplicate phone numbers, paper-occupied stands "
        "with no confirmed payment, stale pending payments, ghost allocations and repeat "
        "applications under the same name.",
    ),
]

# Tools whose successful execution counts as a "verified data" source (contract §7).
# Policy explanations are grounded text, not database lookups, so they don't set the
# verified badge on their own.
DATABASE_TOOLS = frozenset(
    {
        "get_market_overview",
        "get_my_application_status",
        "get_my_payments",
        "get_my_notifications",
        "get_my_financials",
        "get_application_statistics",
        "get_queue_summary",
        "list_recent_allocations",
        "list_pending_verifications",
        "find_suspicious_activity",
    }
)

# --------------------------------------------------------------------------
# registry: name -> implementation
# --------------------------------------------------------------------------

IMPLEMENTATIONS: Dict[str, Callable[[AccessContext, dict], dict]] = {
    "get_market_overview": lambda ctx, args: gateway.market_overview(ctx),
    "explain_market_policy": lambda ctx, args: policy_reference(
        str(args.get("topic", "")).strip().lower()
    ),
    "get_my_application_status": lambda ctx, args: gateway.my_application(ctx),
    "get_my_payments": lambda ctx, args: gateway.my_payments(ctx),
    "get_my_notifications": lambda ctx, args: gateway.my_notifications(ctx),
    "get_my_financials": lambda ctx, args: gateway.my_financials(ctx),
    "get_application_statistics": lambda ctx, args: gateway.application_stats(ctx),
    "get_queue_summary": lambda ctx, args: gateway.queue_summary(ctx),
    "list_recent_allocations": lambda ctx, args: gateway.recent_allocations(ctx),
    "list_pending_verifications": lambda ctx, args: gateway.pending_verifications(ctx),
    "find_suspicious_activity": lambda ctx, args: gateway.suspicious_activity(ctx),
}


def execute_tool(ctx: AccessContext, name: str, arguments: Dict[str, Any]) -> dict:
    """Run one tool with permission enforcement.

    Never raises — failures become structured payloads the LLM can read, so a bad
    turn degrades gracefully instead of crashing the endpoint.
    """
    implementation = IMPLEMENTATIONS.get(name)
    if implementation is None:
        return {"ok": False, "error": f"Unknown tool '{name}'."}

    try:
        return implementation(ctx, arguments or {})
    except PermissionDenied as denied:
        return denial(denied.message)
    except Exception:  # pragma: no cover - defensive: never leak internals to the LLM
        return {
            "ok": False,
            "error": "The records could not be read right now. Please try again shortly.",
        }


# --------------------------------------------------------------------------
# grounded policy text (explanation tool — the assistant's source of truth)
# --------------------------------------------------------------------------

POLICY_LIBRARY: Dict[str, dict] = {
    "allocation": {
        "ok": True,
        "topic": "allocation",
        "summary": (
            "Stands are allocated to verified vendors from a single fair queue: "
            "1) Submit an application from the market map, choosing an available stand. "
            "2) Council administrators review applications in first-in, first-out order. "
            "3) When an application is approved the next suitable stand in your trade's zone is reserved. "
            "4) You confirm the allocation and complete payment. "
            "5) A handover on site is verified before the stand becomes yours. "
            "Every step is written to the audit log."
        ),
        "points": [
            "You keep your queue position while your application is pending.",
            "Only available stands can be requested — occupied or reserved stands cannot be applied for.",
            "The StandProof Assistant cannot allocate stands or change your position; administrators do that.",
        ],
    },
    "payments": {
        "ok": True,
        "topic": "payments",
        "summary": (
            "When your stand is allocated and you accept it, a payment record is created for the "
            "stand levy and paid through the paired mobile-money provider (DevDraft). A council "
            "administrator verifies the payment before permits are issued, and the platform's "
            "guarantee is that money only moves after the allocation and handover conditions are "
            "met. Payment records and receipts live in your dashboard, and statuses are limited "
            "to pending, successful, failed, refunded or disputed as recorded in the database."
        ),
        "points": [
            "Check 'My payments' in this chat or your dashboard for the latest status.",
            "The Assistant never confirms payments in chat — confirmation happens in the admin verification screens.",
            "Keep your receipt number; it is how permits and audits trace your payment.",
        ],
    },
    "permits": {
        "ok": True,
        "topic": "permits",
        "summary": (
            "After a payment is verified as successful, a digital permit with a QR code is issued "
            "for your stand. The QR code can be re-scanned at any time to verify the permit against "
            "the allocation and payment records. Permits are viewable in the vendor dashboard."
        ),
        "points": [
            "Permit numbers follow the platform's permit format (PAM-PERMIT-…).",
            "If a permit fails verification, bring your receipt to the council office.",
        ],
    },
    "verification": {
        "ok": True,
        "topic": "verification",
        "summary": (
            "Before you start trading, a handover must be verified: you and a council official "
            "confirm the physical handover of the stand, matching it to the allocation record. "
            "Administrators also verify payments. Verified handovers are what let a stand legally "
            "change occupancy."
        ),
        "points": [
            "Never pay anyone privately for a stand promise — payments follow verified allocations only.",
            "The audit log records who verified what and when.",
        ],
    },
    "reports": {
        "ok": True,
        "topic": "reports",
        "summary": (
            "If someone demands money, offers to sell a queue position, or a stand looks falsely "
            "occupied, report it. Use the 'Report Corruption' page to file a report with a category, "
            "description and optional location/contact email. Reports go to council administrators "
            "and are visible in their verification queue."
        ),
        "points": [
            "The Assistant cannot file corruption reports — do it from the reports page so it gets a record.",
            "You can report anonymously; contact email is optional.",
        ],
    },
}


def policy_reference(topic: str) -> dict:
    if topic in POLICY_LIBRARY:
        return POLICY_LIBRARY[topic]
    return {
        "ok": True,
        "topic": "index",
        "summary": "Policy topics available: allocation, payments, permits, verification, reports.",
    }
