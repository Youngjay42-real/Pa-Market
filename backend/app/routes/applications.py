"""Applications: vendor submission queue + admin review."""
from flask import Blueprint, g, jsonify, request

from ..constants import ApplicationStatus, HandoverRole
from ..errors import ApiError
from ..extensions import db
from ..models import Allocation, Application, User, Vendor
from ..services.allocation_service import AllocationService
from ..services.auth_service import current_user, require_roles

applications_bp = Blueprint("applications", __name__)

VIEWABLE_STATUSES = [
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.UNDER_REVIEW,
    ApplicationStatus.APPROVED,
    ApplicationStatus.ALLOCATED,
    ApplicationStatus.REJECTED,
]


def application_to_dict(app: Application, include_vendor: bool = False) -> dict:
    payload = {
        "id": app.id,
        "vendor_id": app.vendor_id,
        "status": app.status,
        "queue_position": app.queue_position,
        "business_type": app.business_type,
        "preferred_zone": app.preferred_zone,
        "notes": app.notes,
        "decision_reason": app.decision_reason,
        "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
        "created_at": app.created_at.isoformat(),
    }
    if include_vendor:
        vendor: Vendor = app.vendor
        payload["vendor"] = {
            "id": vendor.id,
            "nrc": vendor.nrc,
            "full_name": vendor.full_name,
            "phone": vendor.phone,
            "business_type": vendor.business_type,
            "preferred_zone": vendor.preferred_zone,
            "status": vendor.status,
        }
    return payload


def _vendor_or_404(user: User) -> Vendor:
    vendor = db.session.query(Vendor).filter_by(user_id=user.id).first()
    if vendor is None:
        raise ApiError(404, "vendor_profile_missing", "No vendor profile exists for this account.")
    return vendor


@applications_bp.post("")
@require_roles("vendor")
def submit_application():
    body = request.get_json(silent=True) or {}
    from ..utils.validation import business_type, preferred_zone, clean_text

    vendor = _vendor_or_404(g.current_user)
    payload = {
        "business_type": business_type(body.get("business_type")),
        "preferred_zone": preferred_zone(body.get("preferred_zone")),
        "notes": clean_text(body.get("notes"), 500, "notes"),
    }
    application = AllocationService.create_application(
        vendor, payload, actor=g.current_user.id, actor_role=g.current_user.role
    )
    db.session.commit()
    return jsonify(application_to_dict(application)), 201


@applications_bp.get("/mine")
@require_roles("vendor")
def my_applications():
    vendor = _vendor_or_404(g.current_user)
    rows = (
        db.session.query(Application)
        .filter(Application.vendor_id == vendor.id)
        .order_by(Application.created_at.desc())
        .limit(50)
        .all()
    )
    allocation_id_by_application = {
        alloc.application_id: alloc.id
        for alloc in db.session.query(Allocation).filter(Allocation.vendor_id == vendor.id)
    }
    payload = []
    for app_row in rows:
        item = application_to_dict(app_row)
        item["allocation_id"] = allocation_id_by_application.get(app_row.id)
        payload.append(item)
    return jsonify({"applications": payload})


@applications_bp.get("")
@require_roles("admin")
def list_applications():
    status = request.args.get("status", "").strip()
    query = db.session.query(Application)
    if status:
        query = query.filter(Application.status == status)
    rows = (
        query.order_by(Application.queue_position.asc().nullslast(), Application.created_at.asc())
        .limit(200)
        .all()
    )
    return jsonify({"applications": [application_to_dict(a, include_vendor=True) for a in rows]})


@applications_bp.get("/<application_id>")
@require_roles("admin", "vendor")
def application_detail(application_id: str):
    application = db.session.get(Application, application_id)
    if application is None:
        raise ApiError(404, "not_found", "Application not found.")
    if g.current_user.role != "admin":
        vendor = _vendor_or_404(g.current_user)
        if application.vendor_id != vendor.id:
            raise ApiError(403, "forbidden", "You can only view your own applications.")
    return jsonify(application_to_dict(application, include_vendor=g.current_user.role == "admin"))


@applications_bp.post("/<application_id>/review")
@require_roles("admin")
def review_application(application_id: str):
    body = request.get_json(silent=True) or {}
    decision = str(body.get("decision", "")).strip().lower()
    reason = str(body.get("reason", "")).strip() or None
    application = db.session.get(Application, application_id)
    if application is None:
        raise ApiError(404, "not_found", "Application not found.")
    AllocationService.review_application(application, decision, g.current_user, reason)
    db.session.commit()
    return jsonify(application_to_dict(application, include_vendor=True))
