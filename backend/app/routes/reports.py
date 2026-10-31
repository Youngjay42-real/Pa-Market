"""Anonymous whistleblower reports (public write, admin-only reads)."""
import secrets
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request

from ..errors import ApiError
from ..extensions import db, limiter
from ..models import CorruptionReport
from ..services.audit_service import AuditService
from ..services.auth_service import require_roles
from ..utils.validation import clean_text

reports_bp = Blueprint("reports", __name__)

REPORT_CATEGORIES = ("bribe_request", "favouritism", "fake_documents", "dupe_application", "other")


def report_to_dict(report: CorruptionReport) -> dict:
    return {
        "id": report.id,
        "reference": report.reference,
        "category": report.category,
        "location": report.location,
        "status": report.status,
        "created_at": report.created_at.isoformat(),
        "description": report.description,   # admin view
        "contact_email": report.contact_email,
    }


@reports_bp.post("")
@limiter.limit(lambda: current_app.config["PUBLIC_WRITE_RATELIMIT"])
def submit_report():
    body = request.get_json(silent=True) or {}
    category = str(body.get("category", "")).strip()
    if category not in REPORT_CATEGORIES:
        raise ApiError(400, "invalid_category", "Unknown report category.", {"allowed": list(REPORT_CATEGORIES)})
    description = clean_text(body.get("description"), 2000, "description")
    if not description or len(description) < 10:
        raise ApiError(400, "description_too_short", "Describe what happened (at least 10 characters).")

    report = CorruptionReport(
        reference=f"WBR-{datetime.now(timezone.utc).strftime('%y%m%d')}-{secrets.token_hex(3).upper()}",
        category=category,
        description=description,
        location=clean_text(body.get("location"), 160, "location"),
        contact_email=clean_text(body.get("contact_email"), 160, "contact_email"),
    )
    db.session.add(report)
    db.session.commit()

    AuditService.record(
        "REPORT_RECEIVED", actor="anonymous", entity_type="report", entity_id=report.id,
        details=f"Category {report.category} (reference {report.reference}).",
    )
    db.session.commit()
    # Public response excludes the description to avoid leaking on shared screens.
    return jsonify(
        {
            "reference": report.reference,
            "message": "Report received. Thank you — the council reviews every report.",
        }
    ), 201


@reports_bp.get("")
@require_roles("admin")
def list_reports():
    status = request.args.get("status", "").strip()
    query = db.session.query(CorruptionReport)
    if status:
        query = query.filter(CorruptionReport.status == status)
    rows = query.order_by(CorruptionReport.created_at.desc()).limit(200).all()
    return jsonify({"reports": [report_to_dict(r) for r in rows]})


@reports_bp.post("/<report_id>/status")
@require_roles("admin")
def update_report_status(report_id: str):
    body = request.get_json(silent=True) or {}
    status = str(body.get("status", "")).strip()
    if status not in ("received", "under_review", "resolved", "dismissed"):
        raise ApiError(400, "invalid_status", "status must be received/under_review/resolved/dismissed.")
    report = db.session.get(CorruptionReport, report_id)
    if report is None:
        raise ApiError(404, "not_found", "Report not found.")
    report.status = status
    AuditService.record(
        "REPORT_STATUS_CHANGED", actor=g.current_user.id, actor_role="admin",
        entity_type="report", entity_id=report.id, details=f"Status: {status}.",
    )
    db.session.commit()
    return jsonify(report_to_dict(report))
