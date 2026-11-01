"""Allocations: create, list, accept, handover confirmation + permit."""
from flask import Blueprint, Response, g, jsonify, request

from ..constants import AllocationStatus, HandoverRole
from ..errors import ApiError
from ..extensions import db
from ..models import Allocation, Application, Payment, Stand
from ..services.allocation_service import AllocationService
from ..services.auth_service import current_user, require_roles

allocations_bp = Blueprint("allocations", __name__)

HISTORY_STATUSES = ["offered", "accepted", "handover_confirmed", "completed", "cancelled", "expired"]


def allocation_to_dict(alloc: Allocation, public: bool = False) -> dict:
    payload = {
        "id": alloc.id,
        "application_id": alloc.application_id,
        "stand_id": alloc.stand_id,
        "vendor_id": alloc.vendor_id,
        "status": alloc.status,
        "fee_amount": f"{alloc.fee_amount:.2f}",
        "currency": alloc.currency,
        "offered_at": alloc.offered_at.isoformat(),
        "offer_expires_at": alloc.offer_expires_at.isoformat() if alloc.offer_expires_at else None,
        "accepted_at": alloc.accepted_at.isoformat() if alloc.accepted_at else None,
        "handover": {
            "vendor": (
                {
                    "confirmed_at": vendor_conf.confirmed_at.isoformat(),
                    "meeting_location": vendor_conf.meeting_location,
                }
                if (vendor_conf := alloc.confirmation_by("vendor")) is not None
                else None
            ),
            "official": (
                {
                    "confirmed_at": official_conf.confirmed_at.isoformat(),
                    "meeting_location": official_conf.meeting_location,
                }
                if (official_conf := alloc.confirmation_by("official")) is not None
                else None
            ),
        },
        "permit_code": alloc.permit_code,
        "completed_at": alloc.completed_at.isoformat() if alloc.completed_at else None,
        "cancelled_reason": alloc.cancelled_reason,
        "stand": {
            "id": alloc.stand.id,
            "code": alloc.stand.code,
            "zone": alloc.stand.zone,
            "row": alloc.stand.row,
            "col": alloc.stand.col,
            "status": alloc.stand.status,
        },
        "payments": [PaymentServicePaymentRef(p) for p in alloc.payments],
    }
    if public:
        payload["payments"] = [
            {"id": p.id, "status": p.status, "amount": f"{p.amount:.2f}"} for p in alloc.payments
        ]
    return payload


def PaymentServicePaymentRef(payment):  # minimal inline projection
    return {"id": payment.id, "status": payment.status, "amount": f"{payment.amount:.2f}"}


def _load_allocation(allocation_id: str) -> Allocation:
    allocation = db.session.get(Allocation, allocation_id)
    if allocation is None:
        raise ApiError(404, "not_found", "Allocation not found.")
    return allocation


@allocations_bp.post("")
@require_roles("admin")
def create_allocation():
    body = request.get_json(silent=True) or {}
    application_id = str(body.get("application_id", ""))
    stand_id = str(body.get("stand_id", "") or "")
    auto_assign = bool(body.get("auto_assign", False)) or not stand_id

    application = db.session.get(Application, application_id)
    if application is None:
        raise ApiError(404, "not_found", "Application not found.")
    if auto_assign:
        allocation = AllocationService.assign_stand(application, g.current_user)
    else:
        stand = db.session.get(Stand, stand_id)
        if stand is None:
            raise ApiError(404, "not_found", "Stand not found.")
        allocation = AllocationService.create_allocation(application, stand, g.current_user)
    db.session.commit()
    return jsonify(allocation_to_dict(allocation)), 201


@allocations_bp.get("")
@require_roles("admin")
def list_allocations():
    status = request.args.get("status", "").strip()
    query = db.session.query(Allocation)
    if status:
        query = query.filter(Allocation.status == status)
    rows = query.order_by(Allocation.offered_at.desc()).limit(200).all()
    return jsonify({"allocations": [allocation_to_dict(a) for a in rows]})


@allocations_bp.get("/mine")
@require_roles("vendor")
def my_allocations():
    from ..models import Vendor

    vendor = db.session.query(Vendor).filter_by(user_id=g.current_user.id).first()
    if vendor is None:
        return jsonify({"allocations": []})
    rows = (
        db.session.query(Allocation)
        .filter(Allocation.vendor_id == vendor.id)
        .order_by(Allocation.offered_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({"allocations": [allocation_to_dict(a) for a in rows]})


@allocations_bp.get("/<allocation_id>")
@require_roles("admin", "vendor")
def allocation_detail(allocation_id: str):
    allocation = _load_allocation(allocation_id)
    if g.current_user.role != "admin":
        if allocation.vendor.user_id != g.current_user.id:
            raise ApiError(403, "forbidden", "This allocation belongs to another vendor.")
    return jsonify(allocation_to_dict(allocation))


@allocations_bp.post("/<allocation_id>/accept")
@require_roles("vendor")
def accept_allocation(allocation_id: str):
    allocation = _load_allocation(allocation_id)
    if allocation.vendor.user_id != g.current_user.id:
        raise ApiError(403, "forbidden", "Accept your own allocation only.")
    AllocationService.accept_allocation(allocation, g.current_user)
    db.session.commit()
    return jsonify(allocation_to_dict(allocation))


@allocations_bp.post("/<allocation_id>/handover")
@require_roles("vendor", "admin")
def confirm_handover(allocation_id: str):
    allocation = _load_allocation(allocation_id)
    body = request.get_json(silent=True) or {}
    if g.current_user.role == "vendor":
        role = HandoverRole.VENDOR
        if allocation.vendor.user_id != g.current_user.id:
            raise ApiError(403, "forbidden", "This allocation belongs to another vendor.")
    else:
        role = HandoverRole.OFFICIAL
    AllocationService.confirm_handover(
        allocation, role, g.current_user,
        meeting_location=str(body.get("meeting_location") or "")[:160] or None,
        notes=str(body.get("notes") or "") or None,
    )
    db.session.commit()
    return jsonify(allocation_to_dict(allocation))


@allocations_bp.get("/<allocation_id>/eligibility")
@require_roles("admin", "vendor")
def payment_eligibility(allocation_id: str):
    allocation = _load_allocation(allocation_id)
    if g.current_user.role != "admin" and allocation.vendor.user_id != g.current_user.id:
        raise ApiError(403, "forbidden", "This allocation belongs to another vendor.")
    verdict = AllocationService.eligibility(allocation)
    return jsonify({"allocation_id": allocation.id, **verdict})


@allocations_bp.get("/<allocation_id>/permit")
@require_roles("admin", "vendor")
def allocation_permit(allocation_id: str):
    allocation = _load_allocation(allocation_id)
    if g.current_user.role != "admin" and allocation.vendor.user_id != g.current_user.id:
        raise ApiError(403, "forbidden", "This allocation belongs to another vendor.")
    if allocation.status != AllocationStatus.COMPLETED or not allocation.permit_code:
        raise ApiError(409, "permit_unavailable",
                       "The permit issues only after the stand levy payment is verified.")
    return jsonify(
        {
            "permit_code": allocation.permit_code,
            "allocation_id": allocation.id,
            "vendor_name": allocation.vendor.full_name,
            "vendor_nrc": allocation.vendor.nrc,
            "stand_code": allocation.stand.code,
            "zone": allocation.stand.zone,
            "issued_at": allocation.completed_at.isoformat() if allocation.completed_at else None,
        }
    )


@allocations_bp.get("/<allocation_id>/permit.pdf")
@require_roles("admin", "vendor")
def allocation_permit_pdf(allocation_id: str):
    """Downloadable PDF permit — the same contract as /permit, as a document."""
    allocation = _load_allocation(allocation_id)
    if g.current_user.role != "admin" and allocation.vendor.user_id != g.current_user.id:
        raise ApiError(403, "forbidden", "This allocation belongs to another vendor.")
    if allocation.status != AllocationStatus.COMPLETED or not allocation.permit_code:
        raise ApiError(409, "permit_unavailable",
                       "The permit issues only after the stand levy payment is verified.")
    from ..utils.permit_pdf import build_permit_pdf

    pdf = build_permit_pdf(
        permit_code=allocation.permit_code,
        vendor_name=allocation.vendor.full_name,
        vendor_nrc=allocation.vendor.nrc,
        stand_code=allocation.stand.code,
        zone=allocation.stand.zone,
        fee_amount=f"{allocation.fee_amount:.2f}",
        currency=allocation.currency,
        issued_at=allocation.completed_at,
    )
    response = Response(pdf, mimetype="application/pdf")
    response.headers["Content-Disposition"] = (
        f"attachment; filename=PaMarket-Permit-{allocation.permit_code}.pdf"
    )
    return response
