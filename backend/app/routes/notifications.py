"""Vendor dashboard notifications."""
from flask import Blueprint, g, jsonify, request

from ..errors import ApiError
from ..extensions import db
from ..models import Notification
from ..services.auth_service import require_roles
from ..services.notification_service import NotificationService

notifications_bp = Blueprint("notifications", __name__)


def notification_to_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "message": n.message,
        "payload": n.payload,
        "read": n.read,
        "created_at": n.created_at.isoformat(),
    }


@notifications_bp.get("")
@require_roles("vendor", "admin")
def my_notifications():
    unread_only = str(request.args.get("unread_only", "false")).lower() == "true"
    rows = NotificationService.list_for(g.current_user.id, unread_only=unread_only)
    return jsonify(
        {
            "notifications": [notification_to_dict(n) for n in rows],
            "unread": NotificationService.unread_count(g.current_user.id),
        }
    )


@notifications_bp.post("/<notification_id>/read")
@require_roles("vendor", "admin")
def mark_read(notification_id: str):
    if not NotificationService.mark_read(g.current_user.id, notification_id):
        raise ApiError(404, "not_found", "Notification not found.")
    db.session.commit()
    return jsonify({"status": "ok"})
