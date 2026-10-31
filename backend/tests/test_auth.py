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


def test_bootstrap_admin_creates_account_and_is_idempotent(app, client):
    password = "render-generated-secret-987"
    app.config.update(
        ADMIN_BOOTSTRAP_PHONE="0776596009",
        ADMIN_BOOTSTRAP_NAME="Pa Market Administrator",
        ADMIN_BOOTSTRAP_PASSWORD=password,
    )
    runner = app.test_cli_runner()

    created = runner.invoke(args=["bootstrap-admin"])
    assert created.exit_code == 0, created.output
    assert password not in created.output

    with app.app_context():
        admin = db.session.query(User).filter_by(phone="0776596009").one()
        original_hash = admin.password_hash
        assert admin.role == "admin"
        assert admin.full_name == "Pa Market Administrator"
        assert original_hash != password

    repeated = runner.invoke(args=["bootstrap-admin"])
    assert repeated.exit_code == 0, repeated.output
    assert "already exists" in repeated.output

    with app.app_context():
        admin = db.session.query(User).filter_by(phone="0776596009").one()
        assert admin.password_hash == original_hash

    response = client.post(
        "/api/v1/auth/login",
        json={"phone": "0776596009", "password": password},
    )
    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == "admin"


def test_bootstrap_admin_fails_for_existing_vendor_phone(app):
    from app.services.auth_service import hash_password

    with app.app_context():
        db.session.add(
            User(
                phone="0776596009",
                full_name="Existing vendor",
                password_hash=hash_password("vendorpass"),
                role="vendor",
            )
        )
        db.session.commit()

    app.config.update(
        ADMIN_BOOTSTRAP_PHONE="0776596009",
        ADMIN_BOOTSTRAP_NAME="Pa Market Administrator",
        ADMIN_BOOTSTRAP_PASSWORD="render-generated-secret-987",
    )
    result = app.test_cli_runner().invoke(args=["bootstrap-admin"])
    assert result.exit_code != 0
    assert "already used by a non-admin account" in result.output


def test_bootstrap_admin_updates_existing_admin_password_from_env(app, client):
    from app.services.auth_service import hash_password

    with app.app_context():
        db.session.add(
            User(
                phone="0776596009",
                full_name="Council Administrator",
                password_hash=hash_password("previous-private-password"),
                role="admin",
            )
        )
        db.session.commit()

    password = "new-private-password-987"
    app.config.update(
        ADMIN_BOOTSTRAP_PHONE="0776596009",
        ADMIN_BOOTSTRAP_NAME="Council Administrator",
        ADMIN_BOOTSTRAP_PASSWORD=password,
    )
    result = app.test_cli_runner().invoke(args=["bootstrap-admin"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "Configured admin password updated."

    assert client.post(
        "/api/v1/auth/login",
        json={"phone": "0776596009", "password": "previous-private-password"},
    ).status_code == 401
    response = client.post(
        "/api/v1/auth/login",
        json={"phone": "0776596009", "password": password},
    )
    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == "admin"
