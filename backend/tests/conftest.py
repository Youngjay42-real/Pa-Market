"""Pytest fixtures: isolated app instances with a file-backed SQLite DB."""
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.update(
    {
        "APP_NAME": "PaMarket",
        "SECRET_KEY": "test-secret",
        "JWT_SECRET_KEY": "test-jwt-secret",
        "DEVDRAFT_MODE": "sandbox",
        "DEVDRAFT_WEBHOOK_SECRET": "test-webhook-signing-secret",
        "PAYMENT_MAX_PER_TRANSACTION": "5.00",
        "PAYMENT_MAX_TEAM_TOTAL": "50.00",
        "ALLOW_DEMO_SEED": "false",
    }
)

from app import create_app  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from app.services.audit_service import AuditService  # noqa: E402


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'test.db'}")
    application = create_app("testing")
    application.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path/'test.db'}"
    application.config.update(
        {
            "DEVDRAFT_MODE": "sandbox",
            "TESTING": True,
            "DEVDRAFT_WEBHOOK_SECRET": "test-webhook-signing-secret",
        }
    )
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_token(client, app):
    """Creates an admin directly in the DB (no self-service admin signup)."""
    from app.extensions import db
    from app.models import User
    from app.services.auth_service import hash_password

    with app.app_context():
        admin = User(
            phone="0776596009",
            full_name="Council Admin",
            password_hash=hash_password("adminpass"),
            role="admin",
        )
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    response = client.post(
        "/api/v1/auth/login", json={"phone": "0776596009", "password": "adminpass"}
    )
    assert response.status_code == 200
    return response.get_json()["token"]


@pytest.fixture()
def vendor_token(client, app):
    """A registered vendor (public signup endpoint)."""
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "phone": "0977123456",
            "full_name": "Mary Banda",
            "password": "vendorpass",
            "nrc": "123456/78/1",
            "business_type": "Food & Fresh Produce",
        },
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["token"]


@pytest.fixture()
def stands(app):
    """A handful of available stands for allocation scenarios."""
    from app.extensions import db
    from app.models import Stand
    from decimal import Decimal

    fees = Decimal("5.00")
    with app.app_context():
        zones = ["Textiles", "Hardware", "Food Court"] + ["Produce"] * 10
        for index, zone in enumerate(zones):
            db.session.add(
                Stand(code=f"ST-1{index + 1:02d}",
                      row=index, col=0, zone=zone,
                      status="available", fee_amount=fees)
            )
        db.session.commit()


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

