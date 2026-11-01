"""Read-only data gateway — every database read the chatbot can perform.

Design rules (CHATBOT_CONTRACT.md §6):

* Every function receives an :class:`AccessContext`. Query scoping comes from the
  context's server-bound identity — there are no parameters that allow one caller
  to request another vendor's records.
* Amounts are returned as formatted strings ("ZMW 5.00"); the chatbot performs no
  floating-point arithmetic and never stores it.
* Dates come back as readable strings plus age helpers where relevant.
* All queries are SELECT-only.
* Rows are normalised into plain dicts immediately (``row._mapping``) so nothing
  else in the package depends on SQLAlchemy row objects.

Schema note (backend lead): this gateway reads the canonical PaMarket tables
(``users``, ``vendors``, ``stands``, ``applications``, ``allocations``,
``payments``, ``notifications``, ``audit_logs``, ``corruption_reports``). The
original prototype's DailySale/TaxPayment/VillageBanking tables do not exist in
PaMarket, so ``get_my_financials`` reports stand-levy totals derived from
``payments`` and ``allocations`` instead. Legibility of statuses follows PaMarket
exactly: applications ``submitted | under_review | approved | allocated |
rejected | cancelled`` and payments ``pending | successful | failed | refunded |
disputed``.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from .data_models import (
    Allocation,
    Application,
    AuditLog,
    Notification,
    Payment,
    Report,
    Stand,
    User,
    Vendor,
)
from .permissions import AccessContext, require_admin, require_vendor

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

MAX_ITEMS_PER_SECTION = 10

# Audit actions that document stand allocation progress (PaMarket vocabulary).
ALLOCATION_ACTIONS = ("ALLOCATION_OFFERED", "ALLOCATION_ACCEPTED")
HANDOVER_ACTIONS = ("HANDOVER_CONFIRMED", "HANDOVER_PARTIAL")

PAYMENT_STATUSES = ("pending", "successful", "failed", "refunded", "disputed")


def _coerce_dt(value: Any) -> Optional[datetime]:
    """Normalises every datetime representation the chatbot may read.

    Handles timezone-aware/naive ``datetime`` objects (canonical columns) and
    ISO-8601 strings with or without the ``Z`` suffix.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(value: Any) -> Optional[str]:
    dt = _coerce_dt(value)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else None


def _age_words(value: Any, now: datetime) -> str:
    dt = _coerce_dt(value)
    if not dt:
        return "unknown date"
    delta = now - dt
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min ago"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours} h ago"
    days = int(hours // 24)
    return f"{days} days ago"


def _hours_since(value: Any, now: datetime) -> Optional[float]:
    dt = _coerce_dt(value)
    if not dt:
        return None
    return round((now - dt).total_seconds() / 3600, 1)


def _money(amount: Any, currency: Any = "ZMW") -> str:
    try:
        total = float(Decimal(str(amount or 0)))
    except (TypeError, ValueError, InvalidOperation):
        total = 0.0
    # Formatting only — no arithmetic for decisions; string output per contract.
    return f"{currency or 'ZMW'} {total:,.2f}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rows(ctx: AccessContext, query) -> List[Dict[str, Any]]:
    """Execute a select and normalise each row to a plain dict.

    Handles ORM entity selects (``select(Model)`` → model column names) as well
    as plain column lists.
    """
    return [_normalise(row) for row in ctx.session.execute(query).all()]


def _normalise(row: Any) -> Dict[str, Any]:
    mapping = row._mapping
    instances = [value for value in mapping.values() if hasattr(value, "_sa_instance_state")]
    if len(mapping) == 1 and instances:
        obj = instances[0]
        return {column.name: getattr(obj, column.name) for column in type(obj).__table__.columns}
    return dict(mapping)


def _vendor_by_nrc(ctx: AccessContext, nrc: str) -> Optional[dict]:
    rows = _rows(ctx, select(Vendor).where(Vendor.nrc == (nrc or "").strip()))
    return rows[0] if rows else None


def _payments_for_vendor_nrc(ctx: AccessContext, nrc: str) -> List[Dict[str, Any]]:
    """All payments belonging to the vendor behind ``nrc`` (SELECT-only join)."""
    vendor = _vendor_by_nrc(ctx, nrc)
    if not vendor:
        return []
    return _rows(ctx, select(Payment).where(Payment.vendor_id == vendor["id"]))


def _successful_payment_nrcs(ctx: AccessContext) -> set:
    """NRCs whose vendor has at least one successful stand-levy payment."""
    paid_nrcs: set = set()
    vendors: Dict[str, str] = {v["id"]: v["nrc"] for v in _rows(ctx, select(Vendor))}
    payments = _rows(
        ctx,
        select(Payment).where(Payment.status.in_(["successful", "completed", "paid"])),
    )
    for p in payments:
        nrc = vendors.get(p.get("vendor_id") or "")
        if nrc:
            paid_nrcs.add(nrc)
    return paid_nrcs


def _stand_summary(stand: dict) -> dict:
    return {
        "id": stand.get("code"),
        "zone": stand.get("zone"),
        "status": (stand.get("status") or "").lower(),
        "allocatedAt": _iso(stand.get("allocated_at")),
    }


# --------------------------------------------------------------------------
# public tools (guest + everyone)
# --------------------------------------------------------------------------


def market_overview(ctx: AccessContext) -> dict:
    now = _now()
    stands = _rows(ctx, select(Stand))
    status_counts = Counter((s.get("status") or "unknown").lower() for s in stands)

    zone_rows: List[dict] = []
    zones: Dict[str, Counter] = {}
    for stand in stands:
        key = (stand.get("zone") or "Unzoned").strip()
        zones.setdefault(key, Counter())[(stand.get("status") or "unknown").lower()] += 1
    for zone in sorted(zones):
        c = zones[zone]
        zone_rows.append(
            {
                "zone": zone,
                "available": c.get("available", 0),
                "occupied": c.get("occupied", 0),
                "reserved": c.get("reserved", 0),
                "maintenance": c.get("maintenance", 0),
            }
        )

    vendors = _rows(ctx, select(Vendor))
    vendor_status = Counter((v.get("status") or "unknown").lower() for v in vendors)

    return {
        "ok": True,
        "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
        "stands": {
            "total": len(stands),
            "available": status_counts.get("available", 0),
            "occupied": status_counts.get("occupied", 0),
            "reserved": status_counts.get("reserved", 0),
            "maintenance": status_counts.get("maintenance", 0),
            "byZone": zone_rows,
        },
        "applications": {
            "pending": vendor_status.get("pending", 0),
            "allocated": vendor_status.get("allocated", 0),
            "rejected": vendor_status.get("rejected", 0),
        },
        "queueDepth": vendor_status.get("pending", 0),
        "note": "Counts come from verified market records (database, just now).",
    }


# --------------------------------------------------------------------------
# vendor tools (own data only)
# --------------------------------------------------------------------------


def my_application(ctx: AccessContext) -> dict:
    require_vendor(ctx)
    nrc = ctx.vendor_key
    vendor = _vendor_by_nrc(ctx, nrc)
    if not vendor:
        return {
            "ok": False,
            "error": "No stand application on file for this account yet. Applying through the map page creates one.",
        }

    # Latest application record for this vendor (if any).
    applications = _rows(
        ctx,
        select(Application)
        .where(Application.vendor_id == vendor["id"])
        .order_by(Application.created_at.desc()),
    )
    application = applications[0] if applications else None

    # The stand currently held by this vendor (stand rows carry the vendor NRC).
    held_stands = sorted(
        (
            s
            for s in _rows(ctx, select(Stand).where(Stand.vendor_nrc == nrc))
            if (s.get("status") or "").lower() in ("occupied", "reserved")
        ),
        key=lambda s: _coerce_dt(s.get("allocated_at")) or _now(),
        reverse=True,
    )
    allocated_stand = held_stands[0] if held_stands else None

    payload = {
        "ok": True,
        "application": {
            "status": (vendor.get("status") or "unknown").lower(),
            "queuePosition": vendor.get("queue_position"),
            "businessType": vendor.get("business_type"),
            "preferredZone": vendor.get("preferred_zone"),
            "paymentMethod": vendor.get("payment_method"),
            "appliedAt": _iso(vendor.get("applied_at")),
            "appliedAgo": _age_words(vendor.get("applied_at"), _now()),
        },
        # PaMarket's application record keeps the precise review status
        # (submitted → under_review → approved/rejected → allocated).
        "applicationStatus": (application.get("status") or "").lower() if application else None,
        "applicationId": application.get("id") if application else None,
    }
    if application is not None and application.get("decision_reason"):
        payload["decisionNote"] = application.get("decision_reason")
    if allocated_stand is not None:
        payload["stand"] = _stand_summary(allocated_stand)
    return payload


def my_payments(ctx: AccessContext) -> dict:
    require_vendor(ctx)
    nrc = ctx.vendor_key
    rows = _payments_for_vendor_nrc(ctx, nrc)
    rows = sorted(rows, key=lambda p: _coerce_dt(p.get("created_at")) or _now(), reverse=True)
    payments = [
        {
            "id": p.get("id"),
            "amount": _money(p.get("amount"), p.get("currency")),
            "status": (p.get("status") or "unknown").lower(),
            "method": p.get("provider"),
            "description": p.get("description"),
            "receiptNo": p.get("receipt_no"),
            "createdAt": _iso(p.get("created_at")),
            "age": _age_words(p.get("created_at"), _now()),
        }
        for p in rows[:MAX_ITEMS_PER_SECTION]
    ]
    return {
        "ok": True,
        "count": len(rows),
        "payments": payments,
        "note": "Payment records from verified database entries.",
    }


def my_notifications(ctx: AccessContext) -> dict:
    require_vendor(ctx)
    user_id = ctx.identity.user_id
    rows = _rows(ctx, select(Notification).where(Notification.user_id == user_id))
    rows = sorted(rows, key=lambda n: _coerce_dt(n.get("created_at")) or _now(), reverse=True)
    items = [
        {
            "type": n.get("type"),
            "title": n.get("title"),
            "message": n.get("message"),
            "read": bool(n.get("read")),
            "createdAt": _iso(n.get("created_at")),
        }
        for n in rows[:MAX_ITEMS_PER_SECTION]
    ]
    unread = sum(1 for n in rows if not n.get("read"))
    return {"ok": True, "total": len(rows), "unread": unread, "latest": items}


def my_financials(ctx: AccessContext) -> dict:
    """Stand-levy summary derived from payments + allocations.

    PaMarket has no daily-sales/tax/village-banking tables, so this tool reports
    what actually exists: levy payments for this vendor and the fee attached to
    their active allocation(s). No arithmetic beyond exact Decimal sums needed
    to present totals; all values are also independently readable in
    ``get_my_payments``.
    """
    require_vendor(ctx)
    nrc = ctx.vendor_key
    now = _now()

    payments = _payments_for_vendor_nrc(ctx, nrc)
    currency = (payments[0].get("currency") if payments else None) or "ZMW"
    totals: Dict[str, Decimal] = {status: Decimal("0") for status in PAYMENT_STATUSES}
    counts: Dict[str, int] = {status: 0 for status in PAYMENT_STATUSES}
    for p in payments:
        status = (p.get("status") or "unknown").lower()
        counts[status] = counts.get(status, 0) + 1
        if status in totals:
            try:
                totals[status] += Decimal(str(p.get("amount") or 0))
            except InvalidOperation:
                pass

    # Stand fee attached to the vendor's active (non-terminal) allocations.
    vendor = _vendor_by_nrc(ctx, nrc)
    active_allocations = []
    if vendor:
        active_allocations = _rows(
            ctx,
            select(Allocation).where(
                Allocation.vendor_id == vendor["id"],
                Allocation.status.in_(["offered", "accepted", "handover_confirmed"]),
            ),
        )

    payload = {
        "ok": True,
        "currency": currency,
        "standLevy": {
            "paidTotal": _money(totals["successful"], currency),
            "awaitingVerificationTotal": _money(totals["pending"], currency),
            "refundedTotal": _money(totals["refunded"], currency),
            "disputedCount": counts["disputed"],
            "failedCount": counts["failed"],
            "activeAllocationsWithFee": [
                {
                    "allocationId": a.get("id"),
                    "standId": a.get("stand_id"),
                    "fee": _money(a.get("fee_amount"), a.get("currency")),
                    "status": (a.get("status") or "").lower(),
                    "offeredAt": _iso(a.get("offered_at")),
                }
                for a in active_allocations[:MAX_ITEMS_PER_SECTION]
            ],
        },
        "note": (
            "Only stand-levy records exist in PaMarket. Money never moves in this chat — "
            "payments are initiated after allocation and verified by the council."
        ),
        "generatedAt": now.strftime("%Y-%m-%d %H:%M"),
    }
    return payload


# --------------------------------------------------------------------------
# admin tools
# --------------------------------------------------------------------------


def application_stats(ctx: AccessContext) -> dict:
    require_admin(ctx)
    vendors = _rows(ctx, select(Vendor))
    # "Applications" reflects the allocation queue administrators triage
    # (vendor status: pending → allocated / rejected). The precise application
    # record statuses are reported alongside as ``applicationRecords``.
    status_counts = Counter((v.get("status") or "unknown").lower() for v in vendors)
    vendor_pending = status_counts.get("pending", 0)

    applications = _rows(ctx, select(Application))
    record_status_counts = Counter((a.get("status") or "unknown").lower() for a in applications)
    business_counts = Counter((a.get("business_type") or "Unspecified") for a in applications)

    payments = _rows(ctx, select(Payment))
    payment_status = Counter((p.get("status") or "unknown").lower() for p in payments)

    stands = _rows(ctx, select(Stand))
    stand_status = Counter((s.get("status") or "unknown").lower() for s in stands)

    return {
        "ok": True,
        "generatedAt": _now().strftime("%Y-%m-%d %H:%M"),
        "applications": dict(status_counts),
        "applicationRecords": dict(record_status_counts),
        "businessTypeMix": dict(business_counts.most_common()),
        "standOccupancy": dict(stand_status),
        "payments": dict(payment_status),
        "queueDepth": vendor_pending,
    }


def queue_summary(ctx: AccessContext) -> dict:
    require_admin(ctx)
    rows = _rows(ctx, select(Vendor).where(Vendor.status == "pending"))
    rows = sorted(
        rows,
        key=lambda v: (v.get("queue_position") or 9999, _coerce_dt(v.get("applied_at")) or _now()),
    )
    items = [
        {
            "queuePosition": v.get("queue_position"),
            "vendorName": v.get("full_name"),
            "businessType": v.get("business_type"),
            "preferredZone": v.get("preferred_zone"),
            "paymentMethod": v.get("payment_method"),
            "appliedAt": _iso(v.get("applied_at")),
        }
        for v in rows[:MAX_ITEMS_PER_SECTION]
    ]
    return {
        "ok": True,
        "queueDepth": len(rows),
        "shown": len(items),
        "pendingApplication": items,
        "note": "Vendor phone numbers are hidden in chat; use the admin dashboard for contact details.",
    }


def recent_allocations(ctx: AccessContext) -> dict:
    require_admin(ctx)
    rows = _rows(
        ctx,
        select(AuditLog).where(AuditLog.action.in_(ALLOCATION_ACTIONS + HANDOVER_ACTIONS)),
    )
    rows = sorted(rows, key=lambda a: _coerce_dt(a.get("recorded_at")) or _now(), reverse=True)

    # Resolve audit entity ids (allocation ids) to stand codes for readability.
    allocation_ids = {a.get("entity_id") for a in rows if a.get("entity_id")}
    stand_by_allocation: Dict[str, dict] = {}
    if allocation_ids:
        allocations = _rows(
            ctx, select(Allocation).where(Allocation.id.in_(list(allocation_ids)))
        )
        stand_ids = {a.get("stand_id") for a in allocations if a.get("stand_id")}
        stands: Dict[str, dict] = {}
        if stand_ids:
            stands = {s["id"]: s for s in _rows(ctx, select(Stand).where(Stand.id.in_(list(stand_ids))))}
        for allocation in allocations:
            stand = stands.get(allocation.get("stand_id") or "")
            if stand:
                stand_by_allocation[allocation["id"]] = stand

    items = []
    for a in rows[:MAX_ITEMS_PER_SECTION]:
        stand = stand_by_allocation.get(a.get("entity_id") or "")
        items.append(
            {
                "logId": a.get("id"),
                "action": a.get("action"),
                # display stand code (ST-000) rather than raw uuid when available
                "entityId": (stand or {}).get("code") or a.get("entity_id"),
                "actor": a.get("actor"),
                "details": a.get("details"),
                "timestamp": _iso(a.get("recorded_at")),
                "age": _age_words(a.get("recorded_at"), _now()),
            }
        )
    rows_total = len(rows)
    return {
        "ok": True,
        "count": rows_total,
        "allocations": items,
        "note": "An allocation only becomes final after handover verification and a confirmed payment.",
    }


def pending_verifications(ctx: AccessContext) -> dict:
    require_admin(ctx)
    now = _now()
    payments = _rows(ctx, select(Payment).where(Payment.status == "pending"))
    payment_items = sorted(
        (
            {
                "paymentId": p.get("id"),
                "amount": _money(p.get("amount"), p.get("currency")),
                "method": p.get("provider"),
                "vendorNrc": vendor_nrc_for_payment(ctx, p.get("vendor_id")),
                "createdAt": _iso(p.get("created_at")),
                "waitingHours": _hours_since(p.get("created_at"), now),
            }
            for p in payments
        ),
        key=lambda item: item["waitingHours"] if item["waitingHours"] is not None else -1,
        reverse=True,
    )[:MAX_ITEMS_PER_SECTION]

    reports = _rows(ctx, select(Report))
    recent_reports = sorted(
        reports,
        key=lambda r: _coerce_dt(r.get("created_at")) or now,
        reverse=True,
    )[:5]
    report_items = [
        {
            "category": r.get("category"),
            "location": r.get("location"),
            "createdAt": _iso(r.get("created_at")),
            "age": _age_words(r.get("created_at"), now),
        }
        for r in recent_reports
    ]
    return {
        "ok": True,
        "pendingPaymentCount": len(payments),
        "pendingPayments": payment_items,
        "recentCorruptionReports": report_items,
        "note": "Confirming a payment requires the admin verification screens. The assistant cannot do it.",
    }


def vendor_nrc_for_payment(ctx: AccessContext, vendor_id: Any) -> Optional[str]:
    """Resolve a payment's vendor_id to an NRC for admin review lists."""
    if not vendor_id:
        return None
    rows = _rows(ctx, select(Vendor).where(Vendor.id == vendor_id))
    return rows[0].get("nrc") if rows else None


def suspicious_activity(ctx: AccessContext) -> dict:
    """Deterministic, rule-based integrity flags (no model judgement involved)."""
    require_admin(ctx)
    now = _now()
    findings: List[dict] = []

    vendors = _rows(ctx, select(Vendor))
    users = _rows(ctx, select(User))
    stands = _rows(ctx, select(Stand))
    payments = _rows(ctx, select(Payment))

    paid_nrcs = _successful_payment_nrcs(ctx)

    # 1. duplicate phone numbers across vendor records
    phone_map: Dict[str, List[dict]] = {}
    for v in vendors:
        phone = (v.get("phone") or "").strip()
        if phone:
            phone_map.setdefault(phone, []).append(v)
    dup_phones = {k: vs for k, vs in phone_map.items() if len(vs) > 1}
    if dup_phones:
        findings.append(
            {
                "pattern": "duplicate_phone",
                "severity": "high",
                "occurrences": len(dup_phones),
                "items": [
                    {
                        "phone_last4": k[-4:],
                        "names": sorted({v.get("full_name") or "unknown" for v in vs}),
                        "nrcs": sorted({v.get("nrc") for v in vs if v.get("nrc")}),
                    }
                    for k, vs in list(dup_phones.items())[:MAX_ITEMS_PER_SECTION]
                ],
            }
        )

    # 2. paper-occupied stands: marked occupied long ago with no successful payment
    paper_occupied = []
    for s in stands:
        if (s.get("status") or "").lower() != "occupied":
            continue
        allocated_at = _coerce_dt(s.get("allocated_at"))
        age_days = (now - allocated_at).days if allocated_at else None
        if age_days is None or age_days < 30:
            continue
        if (s.get("vendor_nrc") or "").strip() in paid_nrcs:
            continue
        paper_occupied.append(
            {
                "standId": s.get("code"),
                "zone": s.get("zone"),
                "vendorNrc_tail": (s.get("vendor_nrc") or "")[-4:],
                "allocatedAgeDays": age_days,
            }
        )
    if paper_occupied:
        findings.append(
            {
                "pattern": "paper_occupied_stand",
                "severity": "high",
                "occurrences": len(paper_occupied),
                "items": paper_occupied[:MAX_ITEMS_PER_SECTION],
            }
        )

    # 3. stale pending payments (>72h)
    stale = []
    for p in payments:
        if (p.get("status") or "").lower() != "pending":
            continue
        hours = _hours_since(p.get("created_at"), now)
        if hours is not None and hours > 72:
            stale.append(
                {"paymentId": p.get("id"), "amount": _money(p.get("amount"), p.get("currency")), "waitingHours": hours}
            )
    if stale:
        findings.append(
            {
                "pattern": "stale_pending_payment",
                "severity": "medium",
                "occurrences": len(stale),
                "items": stale[:MAX_ITEMS_PER_SECTION],
            }
        )

    # 4. ghost allocations: occupied stand whose NRC has no vendor/user record
    known_nrcs = {v.get("nrc") for v in vendors if v.get("nrc")} | {
        u.get("nrc") for u in users if u.get("nrc")
    }
    ghosts = []
    for s in stands:
        stand_nrc = (s.get("vendor_nrc") or "").strip()
        if (s.get("status") or "").lower() != "occupied" or not stand_nrc:
            continue
        if stand_nrc not in known_nrcs:
            ghosts.append({"standId": s.get("code"), "zone": s.get("zone"), "recordedAs": s.get("vendor_name")})
    if ghosts:
        findings.append(
            {
                "pattern": "ghost_allocation",
                "severity": "high",
                "occurrences": len(ghosts),
                "items": ghosts[:MAX_ITEMS_PER_SECTION],
            }
        )

    # 5. repeat applications under the same full name across different NRCs
    name_map: Dict[str, List[dict]] = {}
    for v in vendors:
        key = " ".join((v.get("full_name") or "").lower().split())
        if key:
            name_map.setdefault(key, []).append(v)
    churn = {k: vs for k, vs in name_map.items() if len({v.get("nrc") for v in vs}) > 1}
    if churn:
        findings.append(
            {
                "pattern": "multiple_applications_same_name",
                "severity": "low",
                "occurrences": len(churn),
                "items": [
                    {"name": k, "nrcs": sorted({v.get("nrc") for v in vs})}
                    for k, vs in list(churn.items())[:MAX_ITEMS_PER_SECTION]
                ],
            }
        )

    return {
        "ok": True,
        "checksRun": [
            "duplicate_phone",
            "paper_occupied_stand",
            "stale_pending_payment",
            "ghost_allocation",
            "multiple_applications_same_name",
        ],
        "findings": findings,
        "findingCount": len(findings),
        "note": "Flags are rule-based indicators for human review — the assistant reaches no conclusions.",
    }
