"""Authentication + authorisation behaviour."""
from app.extensions import db
from app.models import User

from .conftest import h


def test_signup_hashes_password(client, app):
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "phone": "0971234567",
            "full_name": "Test Trader",
            "password": "strongpass",
            "nrc": "111111/22/3",
        },
    )
    assert response.status_code == 201
    with app.app_context():
        user = db.session.query(User).filter_by(phone="0971234567").first()
        assert user.password_hash != "strongpass"
        assert user.password_hash.startswith("scrypt:")
        assert user.role == "vendor"
        assert user.vendor is not None


def test_signup_rejects_duplicate_phone(client):
    payload = {
        "phone": "0971234567",
        "full_name": "First",
        "password": "strongpass",
        "nrc": "111111/22/3",
        "business_type": "General Merchandise",
    }
    assert client.post("/api/v1/auth/signup", json=payload).status_code == 201
    duplicate = dict(payload, phone="0971234567", nrc="222222/11/3", full_name="Second")
    response = client.post("/api/v1/auth/signup", json=duplicate)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "phone_taken"


def test_signup_rejects_weak_password_and_bad_nrc(client):
    response = client.post(
        "/api/v1/auth/signup",
        json={"phone": "0971234577", "full_name": "Weak", "password": "short", "nrc": "111111/22/3"},
    )
    assert response.status_code == 400
    response = client.post(
        "/api/v1/auth/signup",
        json={"phone": "0971234578", "full_name": "Bad NRC", "password": "strongpass", "nrc": "bogus"},
    )
    assert response.status_code == 400


def test_login_success_and_failure(client, admin_token):
    response = client.post("/api/v1/auth/login", json={"phone": "0776596009", "password": "wrong"})
    assert response.status_code == 401

    response = client.post("/api/v1/auth/login", json={"phone": "0776596009", "password": "adminpass"})
    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == "admin"


def test_me_requires_token_and_shows_role(client, vendor_token):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    response = client.get("/api/v1/auth/me", headers=h(vendor_token))
    assert response.status_code == 200
    assert response.get_json()["role"] == "vendor"


def test_admin_only_endpoint_blocks_vendors(client, vendor_token, admin_token):
    assert client.get("/api/v1/applications", headers=h(vendor_token)).status_code == 403
    assert client.get("/api/v1/applications", headers=h(admin_token)).status_code == 200


def test_normalizes_260_prefix(client):
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "phone": "+260971234567",
            "full_name": "Prefixed",
            "password": "strongpass",
            "nrc": "333333/44/5",
        },
    )
    assert response.status_code == 201
