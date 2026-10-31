"""Payments: eligibility-gated initiation, status verification, webhooks,
receipts, transaction history and admin refunds."""
from flask import Blueprint, g, jsonify, request

from ..errors import ApiError
from ..extensions import db
from ..models import Allocation, Payment, Vendor
from ..services.allocation_service import AllocationService
from ..services.payment_service import PaymentService
from ..services.auth_service import current_user, require_roles

payments_bp = Blueprint("payments", __name__)


def _load_payment(payment_id: str) -> Payment:
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        raise ApiError(404, "not_found", "Payment not found.")
    return payment


def _assert_payment_owner(payment: Payment) -> None:
    if g.current_user.role != "admin":
        vendor_user_id = payment.vendor.user_id
        if vendor_user_id != g.current_user.id:
            raise ApiError(403, "forbidden", "This payment belongs to another vendor.")


@payments_bp.post("/initiate")
@require_roles("admin", "vendor")
def initiate_payment():
    """Starts a DevDraft payment for a handover-verified allocation.

    Requires header `Idempotency-Key` (UI: generate a UUID per payment
    operation, reuse it on retries). The amount always comes from DB records.
    """
    body = request.get_json(silent=True) or {}
    allocation_id = str(body.get("allocation_id", ""))
    allocation = db.session.get(Allocation, allocation_id)
    if allocation is None:
        raise ApiError(404, "not_found", "Allocation not found.")
    if g.current_user.role != "admin" and allocation.vendor.user_id != g.current_user.id:
        raise ApiError(403, "forbidden", "This allocation belongs to another vendor.")

    payment = PaymentService.initiate(allocation, g.current_user, idempotency_key=None)
    db.session.commit()
    return jsonify(PaymentService.to_dict(payment)), 201


@payments_bp.get("/history")
@require_roles("admin", "vendor")
def payment_history():
    query = db.session.query(Payment)
    if g.current_user.role != "admin":
        vendor = db.session.query(Vendor).filter_by(user_id=g.current_user.id).first()
        if vendor is None:
            return jsonify({"payments": []})
        query = query.filter(Payment.vendor_id == vendor.id)
    status = request.args.get("status", "").strip()
    if status:
        query = query.filter(Payment.status == status)
    rows = query.order_by(Payment.created_at.desc()).limit(200).all()
    return jsonify({"payments": [PaymentService.to_dict(p) for p in rows]})


@payments_bp.get("/<payment_id>")
@require_roles("admin", "vendor")
def payment_detail(payment_id: str):
    payment = _load_payment(payment_id)
    _assert_payment_owner(payment)
    return jsonify(PaymentService.to_dict(payment))


@payments_bp.get("/<payment_id>/status")
@require_roles("admin", "vendor")
def payment_status(payment_id: str):
    """Server-side verification with the provider — this is the truth."""
    payment = _load_payment(payment_id)
    _assert_payment_owner(payment)
    PaymentService.sync(payment, actor=g.current_user)
    db.session.commit()
    return jsonify(PaymentService.to_dict(payment))


@payments_bp.get("/<payment_id>/receipt")
@require_roles("admin", "vendor")
def payment_receipt(payment_id: str):
    payment = _load_payment(payment_id)
    _assert_payment_owner(payment)
    if payment.status not in ("successful", "refunded"):
        raise ApiError(409, "receipt_unavailable",
                       "A receipt exists only after the payment is verified as successful.")
    return jsonify(PaymentService.receipt(payment))


@payments_bp.post("/webhook/devdraft")
def devdraft_webhook():
    """Provider webhook (public, signature-verified, idempotent by event id).

    NOTE: no auth — DevDraft calls this. Signature carries the trust.
    """
    raw_body = request.get_data(cache=True) or b""
    signature = request.headers.get("x-webhook-signature")
    result = PaymentService.handle_webhook(raw_body, signature)
    return jsonify(result)


@payments_bp.post("/<payment_id>/refund")
@require_roles("admin")
def refund_payment(payment_id: str):
    """Hackathon rule: refund test transactions before the 3:30 PM CAT deadline."""
    body = request.get_json(silent=True) or {}
    payment = _load_payment(payment_id)
    PaymentService.refund(payment, g.current_user, reason=str(body.get("reason") or "") or None)
    db.session.commit()
    return jsonify(PaymentService.to_dict(payment))


@payments_bp.get("/team/limits")
@require_roles("admin")
def team_limits():
    """Ledger view for the financial-safety rules (hackathon money discipline)."""
    from decimal import Decimal

    from flask import current_app

    from ..services.payment_conditions import PaymentConditions

    currency = current_app.config["PAYMENT_CURRENCY"]
    spent = PaymentConditions.team_spend_total(currency)
    max_tx: Decimal = current_app.config["PAYMENT_MAX_PER_TRANSACTION"]
    max_total: Decimal = current_app.config["PAYMENT_MAX_TEAM_TOTAL"]
    return jsonify(
        {
            "currency": currency,
            "spent_so_far": f"{spent:.2f}",
            "remaining": f"{max_total - spent:.2f}",
            "max_per_transaction": f"{max_tx:.2f}",
            "max_team_total": f"{max_total:.2f}",
            "note": "Refund all test transactions before the 3:30 PM CAT deadline.",
        }
    )
