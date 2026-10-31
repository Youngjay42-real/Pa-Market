"""Audit log access (admins: full; vendors: own records only) + chain check."""
from flask import Blueprint, g, jsonify, request

from ..extensions import db
from ..models import Allocation, Application, AuditLog, Payment, Vendor
from ..services.audit_service import AuditService
from ..services.auth_service import require_roles

audit_bp = Blueprint("audit", __name__)


def audit_to_dict(entry: AuditLog) -> dict:
    return {
        "id": entry.id,
        "action": entry.action,
        "actor": entry.actor,
        "actor_role": entry.actor_role,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "details": entry.details,
        "recorded_at": entry.recorded_at.isoformat(),
        "prev_hash": entry.prev_hash,
        "entry_hash": entry.entry_hash,
    }


@audit_bp.get("")
@require_roles("admin", "vendor")
def list_audit_logs():
    limit = min(int(request.args.get("limit", 100)), 500)
    offset = max(int(request.args.get("offset", 0)), 0)
    query = db.session.query(AuditLog)

    if g.current_user.role != "admin":
        # Vendors only see audit entries about their own entities.
        vendor = db.session.query(Vendor).filter_by(user_id=g.current_user.id).first()
        if vendor is None:
            return jsonify({"logs": [], "total": 0, "chain": AuditService.verify_chain()})
        own_ids = [vendor.id, vendor.nrc]
        own_ids += [a.id for a in db.session.query(Application).filter_by(vendor_id=vendor.id)]
        own_ids += [p.id for p in db.session.query(Payment).filter_by(vendor_id=vendor.id)]
        own_ids += [a.id for a in db.session.query(Allocation).filter_by(vendor_id=vendor.id)]
        query = query.filter(AuditLog.entity_id.in_(own_ids))

    entity_type = request.args.get("entity_type", "").strip()
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    entity_id = request.args.get("entity_id", "").strip()
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)

    total, rows = AuditService.list_entries(query, limit=limit, offset=offset)
    return jsonify({"logs": [audit_to_dict(r) for r in rows], "total": total})


@audit_bp.get("/verify")
@require_roles("admin")
def verify_chain():
    return jsonify(AuditService.verify_chain())
