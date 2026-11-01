"""Server-side administrator provisioning via environment.

The API contract (docs/API_CONTRACT.md) says administrators are provisioned
server-side — config/env or the seeder, never self-service signup. On Render
there is no shell and demo seeding is disabled, so the deployment sets
ADMIN_PHONE + ADMIN_PASSWORD and the app guarantees the council account
exists (idempotent; existing users keep their password).
"""
import logging
import os

from flask import current_app

log = logging.getLogger(__name__)

_TRUE = ("1", "true", "yes")


def provision_admin_from_env(app) -> None:
    # Read os.environ directly: Flask's app.config only carries named keys from
    # config.py, so arbitrary env vars like ADMIN_* are invisible to it.
    phone = (os.environ.get("ADMIN_PHONE") or "").strip()
    password = (os.environ.get("ADMIN_PASSWORD") or "").strip()
    reset = (os.environ.get("ADMIN_PASSWORD_RESET") or "").strip().lower() in _TRUE
    if not phone or not password:
        return
    with app.app_context():
        from ..extensions import db
        from ..models import User
        from ..services.audit_service import AuditService
        from ..services.auth_service import hash_password

        try:
            existing = db.session.query(User).filter_by(phone=phone).one_or_none()
        except Exception:  # tables not migrated yet — the CLI/build handles it
            log.warning("Admin bootstrap skipped: database not ready yet.")
            return
        if existing is not None:
            if existing.role != "admin":
                log.warning("ADMIN_PHONE %s already registered as a vendor; not modified.", phone)
            elif reset:
                existing.password_hash = hash_password(password)
                db.session.commit()
                AuditService.record(
                    "ADMIN_PASSWORD_RESET", actor="system", entity_type="user", entity_id=existing.id,
                )
                db.session.commit()
                log.info("Password reset for council administrator %s (ADMIN_PASSWORD_RESET=true).", phone)
            return
        if len(password) < 8:
            log.error("ADMIN_PASSWORD must be at least 8 characters; admin not created.")
            return
        admin = User(phone=phone, full_name="Council Administrator", password_hash=hash_password(password), role="admin")
        db.session.add(admin)
        db.session.flush()
        AuditService.record(
            "ADMIN_PROVISIONED", actor="system", entity_type="user", entity_id=admin.id,
        )
        db.session.commit()
        log.info("Council administrator provisioned for %s.", phone)
