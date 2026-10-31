"""Vendor dashboard notifications."""
from ..extensions import db
from ..models import Notification


class NotificationService:
    @staticmethod
    def push(user_id: str, ntype: str, title: str, message: str, payload: dict | None = None) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=ntype,
            title=title,
            message=message,
            payload=payload,
        )
        db.session.add(notification)
        return notification

    @staticmethod
    def list_for(user_id: str, unread_only: bool = False, limit: int = 50):
        q = db.session.query(Notification).filter(Notification.user_id == user_id)
        if unread_only:
            q = q.filter(Notification.read.is_(False))
        return q.order_by(Notification.created_at.desc()).limit(limit).all()

    @staticmethod
    def mark_read(user_id: str, notification_id: str) -> bool:
        notification = db.session.get(Notification, notification_id)
        if notification is None or notification.user_id != user_id:
            return False
        notification.read = True
        return True

    @staticmethod
    def unread_count(user_id: str) -> int:
        return (
            db.session.query(Notification)
            .filter(Notification.user_id == user_id, Notification.read.is_(False))
            .count()
        )
