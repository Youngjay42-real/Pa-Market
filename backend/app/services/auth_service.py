"""Password hashing, JWT identity helpers, role-based access control."""
from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from ..errors import ApiError
from ..extensions import db
from ..models import User


def hash_password(raw: str) -> str:
    """scrypt via Werkzeug — a recognised, salted, stretch-iterated hashing scheme."""
    from werkzeug.security import generate_password_hash

    return generate_password_hash(raw, method="scrypt")


def verify_password(raw: str, stored: str) -> bool:
    from werkzeug.security import check_password_hash

    try:
        return check_password_hash(stored, raw)
    except ValueError:
        return False


def current_user() -> User:
    """Load the authenticated user or raise 401."""
    verify_jwt_in_request()
    user = db.session.get(User, get_jwt_identity())
    if user is None or not user.is_active:
        raise ApiError(401, "unauthorized", "Account not found or disabled.")
    return user


def require_roles(*roles):
    """Decorator enforcing role claims on protected endpoints."""

    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            user = current_user()
            if roles and user.role not in roles:
                raise ApiError(403, "forbidden", "You do not have access to this resource.")
            g.current_user = user
            return fn(*args, **kwargs)

        return decorated

    return wrapper


def role_claim() -> str | None:
    try:
        verify_jwt_in_request()
        return get_jwt().get("role")
    except Exception:
        return None
