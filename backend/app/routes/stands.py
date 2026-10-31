"""Stands: public market-map data + meta (zones/categories) for the frontend."""
from flask import Blueprint, jsonify, request

from ..constants import BUSINESS_CATEGORIES, BUSINESS_CATEGORY_ZONES, MARKET_ZONES
from ..extensions import db
from ..models import Stand
from ..services.auth_service import current_user, require_roles
from ..utils.validation import clean_text

stands_bp = Blueprint("stands", __name__)


def stand_to_dict(stand: Stand) -> dict:
    return {
        "id": stand.id,
        "code": stand.code,
        "row": stand.row,
        "col": stand.col,
        "zone": stand.zone,
        "status": stand.status,
        "vendor_name": stand.vendor_name,
        "vendor_nrc": stand.vendor_nrc,
        "allocated_at": stand.allocated_at.isoformat() if stand.allocated_at else None,
        "hold_expires_at": stand.hold_expires_at.isoformat() if stand.hold_expires_at else None,
        "fee_amount": f"{stand.fee_amount:.2f}",
        "currency": stand.currency,
    }


def _summary(rows) -> list[dict]:
    summary: dict[tuple[str, str], int] = {}
    for zone, status, total in rows:
        summary[(zone, status)] = total
    statuses = ["available", "reserved", "occupied", "maintenance"]
    return [
        {
            "zone": zone,
            "counts": {status: summary.get((zone, status), 0) for status in statuses},
            "total": sum(summary.get((zone, status), 0) for status in statuses),
        }
        for zone in MARKET_ZONES
    ]


@stands_bp.get("")
def list_stands():
    query = db.session.query(Stand)
    zone = request.args.get("zone", "").strip()
    status = request.args.get("status", "").strip()
    search = clean_text(request.args.get("q", ""), 60, "q")
    if zone:
        query = query.filter(Stand.zone == zone)
    if status:
        query = query.filter(Stand.status == status)
    if search:
        like = f"%{search}%"
        query = query.filter(Stand.code.ilike(like))
    limit = min(int(request.args.get("limit", 500)), 500)
    stands = query.order_by(Stand.code).limit(limit).all()
    return jsonify({"stands": [stand_to_dict(s) for s in stands]})


@stands_bp.get("/stats")
def stand_stats():
    """Legend counts queried directly from the DB (fast map hydration)."""
    from sqlalchemy import func

    rows = (
        db.session.query(Stand.zone, Stand.status, func.count())
        .group_by(Stand.zone, Stand.status)
        .all()
    )
    occupied_vendors: int = (
        db.session.query(Stand).filter(Stand.status == "occupied").count()
    )
    return jsonify(
        {"zones": _summary(rows), "occupied_vendors": occupied_vendors}
    )


@stands_bp.get("/available")
def available_stands():
    stands = (
        db.session.query(Stand)
        .filter(Stand.status == "available")
        .order_by(Stand.zone, Stand.code)
        .all()
    )
    return jsonify({"stands": [stand_to_dict(s) for s in stands]})


@stands_bp.get("/meta")
def market_meta():
    return jsonify(
        {
            "zones": list(MARKET_ZONES),
            "business_categories": list(BUSINESS_CATEGORIES),
            "category_zones": {k: list(v) for k, v in BUSINESS_CATEGORY_ZONES.items()},
        }
    )


@stands_bp.get("/<stand_id>")
def stand_detail(stand_id: str):
    stand = db.session.get(Stand, stand_id)
    if stand is None:
        stand = db.session.query(Stand).filter_by(code=stand_id).first()
    if stand is None:
        from ..errors import ApiError

        raise ApiError(404, "not_found", "Stand not found.")
    # Admins see personal details on stands; the public sees occupancy only.
    try:
        user = current_user()
        is_admin = user.role == "admin"
    except Exception:
        is_admin = False
    payload = stand_to_dict(stand)
    if not is_admin:
        payload.pop("vendor_nrc", None)
    return jsonify(payload)
