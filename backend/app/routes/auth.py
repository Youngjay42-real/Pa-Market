"""Authentication: signup, login, logout, me.

Signup creates a User plus a linked Vendor profile. No secret admin codes —
administrators are created by the backend lead (config/env or the seeder).
"""
from flask import Blueprint, current_app, g, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, unset_jwt_cookies

from ..constants import NotificationType
from ..errors import ApiError
from ..extensions import db, limiter
from ..models import User, Vendor
from ..models.base import utcnow
from ..services.audit_service import AuditService
from ..utils.validation import (
    business_type,
    normalize_nrc,
    normalize_phone,
    password_strength,
    clean_text,
)
from ..services.auth_service import hash_password, verify_password
from ..services.notification_service import NotificationService

auth_bp = Blueprint("auth", __name__)


def auth_response(user: User, status: int = 200):
    token = create_access_token(
        identity=user.id, additional_claims={"role": user.role}
    )
    payload = {
        "token": token,
        "token_type": "Bearer",
        "expires_in": int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()),
        "user": {
            "id": user.id,
            "phone": user.phone,
            "full_name": user.full_name,
            "role": user.role,
            "nrc": user.nrc,
            "business_type": user.business_type,
        },
    }
    return jsonify(payload), status


@auth_bp.post("/signup")
@limiter.limit(lambda: current_app.config["AUTH_RATELIMIT"])
def signup():
    body = request.get_json(silent=True) or {}
    phone = normalize_phone(str(body.get("phone", "")).strip())
    full_name = clean_text(body.get("full_name"), 120, "full_name")
    if not full_name:
        raise ApiError(400, "missing_fields", "full_name is required.", {"fields": ["full_name"]})
    password = password_strength(str(body.get("password", "")))
    role = "vendor"  # self-service is vendor-only; admins are provisioned server-side

    if db.session.query(User).filter_by(phone=phone).first() is not None:
        raise ApiError(409, "phone_taken", "An account already uses this phone number.")

    nrc = normalize_nrc(str(body.get("nrc", "")))
    if db.session.query(User).filter_by(nrc=nrc).first() is not None:
        raise ApiError(409, "nrc_taken", "An account already uses this NRC.")
    btype = business_type(body.get("business_type"))

    user = User(
        phone=phone,
        full_name=full_name,
        password_hash=hash_password(password),
        role=role,
        nrc=nrc,
        business_type=btype,
    )
    db.session.add(user)
    db.session.flush()
    vendor = Vendor(
        user_id=user.id,
        nrc=nrc,
        full_name=full_name,
        phone=phone,
        business_type=btype,
        queue_position=0,
        status="registered",
    )
    db.session.add(vendor)
    db.session.commit()

    AuditService.record(
        "USER_REGISTERED", actor=user.id, actor_role=role,
        entity_type="user", entity_id=user.id,
    )
    db.session.commit()
    return auth_response(user, 201)


@auth_bp.post("/login")
@limiter.limit(lambda: current_app.config["AUTH_RATELIMIT"])
def login():
    body = request.get_json(silent=True) or {}
    phone = normalize_phone(str(body.get("phone", "")).strip())
    password = str(body.get("password", ""))

    user = db.session.query(User).filter_by(phone=phone).first()
    if user is None or not verify_password(password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "Wrong phone number or password.")
    if not user.is_active:
        raise ApiError(403, "account_disabled", "This account is disabled. Contact the council.")

    user.last_login_at = utcnow()
    db.session.commit()
    return auth_response(user)


@auth_bp.post("/logout")
@jwt_required()
def logout():
    """JWTs are stateless; the client discards the token. The endpoint exists
    so the frontend flow is explicit and future revocation slots in cleanly."""
    response = jsonify({"message": "Logged out."})
    unset_jwt_cookies(response)
    return response


@auth_bp.get("/me")
@jwt_required()
def me():
    user: User = g.current_user if hasattr(g, "current_user") else None
    if user is None:
        from ..services.auth_service import current_user

        user = current_user()
    vendor = db.session.query(Vendor).filter_by(user_id=user.id).first()
    return jsonify(
        {
            "id": user.id,
            "phone": user.phone,
            "full_name": user.full_name,
            "role": user.role,
            "nrc": user.nrc,
            "business_type": user.business_type,
            "vendor_id": vendor.id if vendor else None,
            "unread_notifications": NotificationService.unread_count(user.id),
        }
    )
