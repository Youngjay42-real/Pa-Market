"""Read-only data gateway — every database read the chatbot can perform.

Design rules (CHATBOT_CONTRACT.md §6):

* Every function receives an :class:`AccessContext`. Query scoping comes from the
  context's server-bound identity — there are no parameters that allow one caller
  to request another vendor's records.
* Amounts are returned as formatted strings ("ZMW 350.00"); the chatbot performs
  no floating-point arithmetic and never stores it.
* Dates come back as readable strings plus age helpers where relevant.
* All queries are SELECT-only.
* Rows are fetched via Core tables and normalised into dicts immediately
  (``row._mapping``) so nothing else in the package depends on SQLAlchemy row
  objects.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select

from .data_models import (
    AuditLog,
    DailySale,
    Notification,
    Payment,
    Report,
    Stand,
    TaxPayment,
    User,
    VillageBankingAccount,
    Vendor,
)
from .permissions import AccessContext, require_admin, require_vendor

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

MAX_ITEMS_PER_SECTION = 10


def _coerce_dt(value: Any) -> Optional[datetime]:
    """Normalises every datetime representation the chatbot may read.

    Handles:
    - timezone-aware/naive ``datetime`` objects (server-side chat tables)
    - Prisma-on-Storage epoch millisecond numbers (``Stand.allocatedAt`` etc.)
    - ISO-8601 strings with or without the ``Z`` suffix
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        millis = float(value)
        if abs(millis) < 1e11:  # seconds
            millis *= 1000
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
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
        total = float(amount or 0)
    except (TypeError, ValueError):
        total = 0.0
    # Formatting only — no arithmetic for decisions; string output per contract.
    return f"{currency or 'ZMW'} {total:,.2f}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rows(ctx: AccessContext, query) -> List[Dict[str, Any]]:
    """Execute a Core select and normalise each row to a plain dict."""
    return [dict(row._mapping) for row in ctx.session.execute(query).all()]


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
    rows = _rows(ctx, select(Vendor).where(Vendor.c.nrc == nrc))
    if not rows:
        return {
            "ok": False,
            "error": "No stand application on file for this account yet. Applying through the map page creates one.",
        }
    vendor = rows[0]

    allocated_stand = None
    if vendor.get("standId"):
        stand_rows = _rows(ctx, select(Stand).where(Stand.c.id == vendor["standId"]))
        if stand_rows:
            allocated_stand = stand_rows[0]

    payload = {
        "ok": True,
        "application": {
            "status": (vendor.get("status") or "unknown").lower(),
            "queuePosition": vendor.get("queuePosition"),
            "businessType": vendor.get("businessType"),
            "preferredZone": vendor.get("preferredZone"),
            "paymentMethod": vendor.get("paymentMethod"),
            "appliedAt": _iso(vendor.get("appliedAt")),
            "appliedAgo": _age_words(vendor.get("appliedAt"), _now()),
        },
    }
    if allocated_stand is not None:
        payload["stand"] = {
            "id": allocated_stand.get("id"),
            "zone": allocated_stand.get("zone"),
            "status": (allocated_stand.get("status") or "").lower(),
            "allocatedAt": _iso(allocated_stand.get("allocatedAt")),
        }
    return payload


def my_payments(ctx: AccessContext) -> dict:
    require_vendor(ctx)
    nrc = ctx.vendor_key
    rows = _rows(ctx, select(Payment).where(Payment.c.vendorNrc == nrc))
    rows = sorted(rows, key=lambda p: _coerce_dt(p.get("createdAt")) or _now(), reverse=True)
    payments = [
        {
            "id": p.get("id"),
            "amount": _money(p.get("amount"), p.get("currency")),
            "status": (p.get("status") or "unknown").lower(),
            "method": p.get("method"),
            "receiptNo": p.get("receiptNo"),
            "createdAt": _iso(p.get("createdAt")),
            "age": _age_words(p.get("createdAt"), _now()),
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
    nrc = ctx.vendor_key
    rows = _rows(ctx, select(Notification).where(Notification.c.vendorNrc == nrc))
    rows = sorted(rows, key=lambda n: _coerce_dt(n.get("createdAt")) or _now(), reverse=True)
    items = [
        {
            "type": n.get("type"),
            "title": n.get("title"),
            "message": n.get("message"),
            "read": bool(n.get("read")),
            "createdAt": _iso(n.get("createdAt")),
        }
        for n in rows[:MAX_ITEMS_PER_SECTION]
    ]
    unread = sum(1 for n in rows if not n.get("read"))
    return {"ok": True, "total": len(rows), "unread": unread, "latest": items}


def my_financials(ctx: AccessContext) -> dict:
    require_vendor(ctx)
    nrc = ctx.vendor_key
    now = _now()

    sales = _rows(ctx, select(DailySale).where(DailySale.c.vendorNrc == nrc))
    unpaid = [s for s in sales if (s.get("status") or "").lower() == "unpaid"]
    unpaid_tax = sum(float(s.get("taxAmount") or 0) for s in unpaid)
    paid_sales = [s for s in sales if (s.get("status") or "").lower() == "paid"]

    taxes = _rows(ctx, select(TaxPayment).where(TaxPayment.c.vendorNrc == nrc))
    taxes = sorted(taxes, key=lambda t: _coerce_dt(t.get("paidAt")) or now, reverse=True)

    accounts = _rows(ctx, select(VillageBankingAccount).where(VillageBankingAccount.c.vendorNrc == nrc))
    account = accounts[0] if accounts else None

    payload = {
        "ok": True,
        "dailySales": {
            "recorded": len(sales),
            "unpaidTaxDue": _money(unpaid_tax),
            "unpaidEntries": len(unpaid),
            "paidEntries": len(paid_sales),
        },
    }
    if taxes:
        t = taxes[0]
        payload["latestTaxPayment"] = {
            "amount": _money(t.get("amount")),
            "receiptNo": t.get("receiptNo"),
            "paidAt": _iso(t.get("paidAt")),
        }
    if account is not None:
        payload["villageBanking"] = {
            "groupId": account.get("groupId"),
            "balance": _money(account.get("balance")),
            "savingsGoal": _money(account.get("savingsGoal")),
            "interestRate": f"{float(account.get('interestRate') or 0) * 100:.1f}% per annum",
        }
    return payload


# --------------------------------------------------------------------------
# admin tools
# --------------------------------------------------------------------------


def application_stats(ctx: AccessContext) -> dict:
    require_admin(ctx)
    vendors = _rows(ctx, select(Vendor))
    status_counts = Counter((v.get("status") or "unknown").lower() for v in vendors)
    business_counts = Counter((v.get("businessType") or "Unspecified") for v in vendors)

    payments = _rows(ctx, select(Payment))
    payment_status = Counter((p.get("status") or "unknown").lower() for p in payments)

    stands = _rows(ctx, select(Stand))
    stand_status = Counter((s.get("status") or "unknown").lower() for s in stands)

    return {
        "ok": True,
        "generatedAt": _now().strftime("%Y-%m-%d %H:%M"),
        "applications": dict(status_counts),
        "businessTypeMix": dict(business_counts.most_common()),
        "standOccupancy": dict(stand_status),
        "payments": dict(payment_status),
        "queueDepth": status_counts.get("pending", 0),
    }


def queue_summary(ctx: AccessContext) -> dict:
    require_admin(ctx)
    rows = _rows(ctx, select(Vendor).where(Vendor.c.status == "pending"))
    rows = sorted(
        rows,
        key=lambda v: (v.get("queuePosition") or 9999, _coerce_dt(v.get("appliedAt")) or _now()),
    )
    items = [
        {
            "queuePosition": v.get("queuePosition"),
            "vendorName": v.get("fullName"),
            "businessType": v.get("businessType"),
            "preferredZone": v.get("preferredZone"),
            "paymentMethod": v.get("paymentMethod"),
            "appliedAt": _iso(v.get("appliedAt")),
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
        select(AuditLog).where(AuditLog.c.action.in_(["STAND_ALLOCATED", "VENDOR_ALLOCATED"])),
    )
    rows = sorted(rows, key=lambda a: _coerce_dt(a.get("timestamp")) or _now(), reverse=True)
    items = [
        {
            "logId": a.get("id"),
            "action": a.get("action"),
            "entityId": a.get("entityId"),
            "actor": a.get("actor"),
            "details": a.get("details"),
            "timestamp": _iso(a.get("timestamp")),
            "age": _age_words(a.get("timestamp"), _now()),
        }
        for a in rows[:MAX_ITEMS_PER_SECTION]
    ]
    return {
        "ok": True,
        "count": len(rows),
        "allocations": items,
        "note": "An allocation only becomes final after handover verification and a confirmed payment.",
    }


def pending_verifications(ctx: AccessContext) -> dict:
    require_admin(ctx)
    now = _now()
    payments = _rows(ctx, select(Payment).where(Payment.c.status == "pending"))
    payment_items = sorted(
        (
            {
                "paymentId": p.get("id"),
                "amount": _money(p.get("amount"), p.get("currency")),
                "method": p.get("method"),
                "vendorNrc": p.get("vendorNrc"),
                "createdAt": _iso(p.get("createdAt")),
                "waitingHours": _hours_since(p.get("createdAt"), now),
            }
            for p in payments
        ),
        key=lambda item: item["waitingHours"] if item["waitingHours"] is not None else -1,
        reverse=True,
    )[:MAX_ITEMS_PER_SECTION]

    reports = _rows(ctx, select(Report))
    recent_reports = sorted(
        reports,
        key=lambda r: _coerce_dt(r.get("createdAt")) or now,
        reverse=True,
    )[:5]
    report_items = [
        {
            "category": r.get("category"),
            "location": r.get("location"),
            "createdAt": _iso(r.get("createdAt")),
            "age": _age_words(r.get("createdAt"), now),
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


def suspicious_activity(ctx: AccessContext) -> dict:
    """Deterministic, rule-based integrity flags (no model judgement involved)."""
    require_admin(ctx)
    now = _now()
    findings: List[dict] = []

    vendors = _rows(ctx, select(Vendor))
    users = _rows(ctx, select(User))
    stands = _rows(ctx, select(Stand))
    payments = _rows(ctx, select(Payment))

    paid_nrcs = {
        p.get("vendorNrc") for p in payments if (p.get("status") or "").lower() == "confirmed"
    }

    # 1. duplicate phone numbers across vendor applications
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
                        "names": sorted({v.get("fullName") or "unknown" for v in vs}),
                        "nrcs": sorted({v.get("nrc") for v in vs if v.get("nrc")}),
                    }
                    for k, vs in list(dup_phones.items())[:MAX_ITEMS_PER_SECTION]
                ],
            }
        )

    # 2. paper-occupied stands: marked occupied long ago with no confirmed payment
    paper_occupied = []
    for s in stands:
        if (s.get("status") or "").lower() != "occupied":
            continue
        allocated_at = _coerce_dt(s.get("allocatedAt"))
        age_days = (now - allocated_at).days if allocated_at else None
        if age_days is None or age_days < 30:
            continue
        if s.get("vendorNrc") in paid_nrcs:
            continue
        paper_occupied.append(
            {
                "standId": s.get("id"),
                "zone": s.get("zone"),
                "vendorNrc_tail": (s.get("vendorNrc") or "")[-4:],
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
        hours = _hours_since(p.get("createdAt"), now)
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
    known_nrcs = {v.get("nrc") for v in vendors} | {u.get("nrc") for u in users if u.get("nrc")}
    ghosts = []
    for s in stands:
        if (s.get("status") or "").lower() != "occupied" or not s.get("vendorNrc"):
            continue
        if s.get("vendorNrc").strip() not in known_nrcs:
            ghosts.append({"standId": s.get("id"), "zone": s.get("zone"), "recordedAs": s.get("vendorName")})
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
        key = " ".join((v.get("fullName") or "").lower().split())
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
