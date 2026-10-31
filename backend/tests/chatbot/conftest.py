"""Shared pytest fixtures for the Market Assistant test suite.

Adapted to PaMarket: builds an isolated SQLite database with the canonical
PaMarket schema (backed by Flask-SQLAlchemy models — see ``app/models``), seeds
representative records, boots the Flask app with the mock (deterministic) LLM
and generous rate limits, and returns a test client. The chatbot-owned tables
(``chat_session`` / ``chat_message``) are created with the same engine by the
chatbot's own metadata.

Store/db shapes follow docs/CHATBOT_CONTRACT.md; the seeded rows intentionally
mirror the contract examples (Mary Banda pending, Chanda Mwansa allocated,
ST-001 the only available stand, a paper-occupied ST-102).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
for candidate in (str(BACKEND_DIR), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from sqlalchemy import insert  # noqa: E402

from app.chatbot import ChatbotService  # noqa: E402
from app.chatbot import database as chatbot_db  # noqa: E402
from app.chatbot.database import make_engine  # noqa: E402
from app.chatbot.llm import RuleBasedLLMClient  # noqa: E402
from app.chatbot.models import Base as ChatBase  # noqa: E402
from app.chatbot.ratelimit import RateLimitRule  # noqa: E402
from app.extensions import set_chatbot_service  # noqa: E402
from app.models import (  # noqa: E402
    Allocation,
    Application,
    AuditLog,
    Base,
    CorruptionReport,
    Notification,
    Payment,
    Stand,
    User,
    Vendor,
)
from app.services.auth_service import hash_password  # noqa: E402

NOW = datetime.now(timezone.utc)

VENDOR_A = {  # "Mary Banda" — pending in the allocation queue
    "id": "user-mary",
    "phone": "0977123456",
    "full_name": "Mary Banda",
    "password_hash": hash_password("pass123"),
    "role": "vendor",
    "nrc": "123456/78/1",
    "business_type": "Vegetables",
    "created_at": NOW - timedelta(days=9),
}
VENDOR_B = {  # second vendor — allocated to a stand
    "id": "user-chanda",
    "phone": "0966444777",
    "full_name": "Chanda Mwansa",
    "password_hash": hash_password("secret7"),
    "role": "vendor",
    "nrc": "999111/22/3",
    "business_type": "Fish/Meat",
    "created_at": NOW - timedelta(days=40),
}
ADMIN = {
    "id": "user-admin",
    "phone": "0776596009",
    "full_name": "Council Administrator",
    "password_hash": hash_password("1234567"),
    "role": "admin",
    "nrc": None,
    "business_type": None,
    "created_at": NOW - timedelta(days=200),
}

VENDOR_A_ID = "vendor-mary"
VENDOR_B_ID = "vendor-chanda"

STAND_AVAILABLE = {  # ST-001 is intentionally the ONLY available stand
    "id": "stand-001",
    "code": "ST-001",
    "row": 0,
    "col": 1,
    "zone": "Produce",
    "status": "available",
    "vendor_name": None,
    "vendor_nrc": None,
    "allocated_at": None,
    "hold_expires_at": None,
    "fee_amount": Decimal("5.00"),
    "currency": "USD",
}
STAND_OCCUPIED = {
    "id": "stand-101",
    "code": "ST-101",
    "row": 2,
    "col": 4,
    "zone": "Textiles",
    "status": "occupied",
    "vendor_name": "Chanda Mwansa",
    "vendor_nrc": "999111/22/3",
    "allocated_at": NOW - timedelta(days=40),
    "hold_expires_at": None,
    "fee_amount": Decimal("5.00"),
    "currency": "USD",
}
STAND_PAPER = {  # occupied 75 days with no successful payment → paper-occupied flag
    "id": "stand-102",
    "code": "ST-102",
    "row": 2,
    "col": 5,
    "zone": "Textiles",
    "status": "occupied",
    "vendor_name": "Paper Holder",
    "vendor_nrc": "888222/55/1",
    "allocated_at": NOW - timedelta(days=75),
    "hold_expires_at": None,
    "fee_amount": Decimal("5.00"),
    "currency": "USD",
}


@pytest.fixture()
def market_db(tmp_path, monkeypatch):
    """Create + seed a throwaway database holding the PaMarket schema."""
    db_path = tmp_path / "market_seed.sqlite3"
    url = f"sqlite:///{db_path}"

    seed_engine = make_engine(url)
    Base.metadata.create_all(seed_engine)      # application tables (PaMarket)
    ChatBase.metadata.create_all(seed_engine)  # chat tables (chatbot-owned)

    with seed_engine.begin() as conn:
        for user in (VENDOR_A, VENDOR_B, ADMIN):
            conn.execute(insert(User).values(user))

        conn.execute(
            insert(Vendor).values(
                id=VENDOR_A_ID,
                user_id=VENDOR_A["id"],
                nrc=VENDOR_A["nrc"],
                full_name=VENDOR_A["full_name"],
                phone=VENDOR_A["phone"],
                queue_position=12,
                status="pending",
                business_type=VENDOR_A["business_type"],
                preferred_zone="Produce",
                payment_method="mtn",
                applied_at=NOW - timedelta(days=9),
            )
        )
        conn.execute(
            insert(Vendor).values(
                id=VENDOR_B_ID,
                user_id=VENDOR_B["id"],
                nrc=VENDOR_B["nrc"],
                full_name=VENDOR_B["full_name"],
                phone=VENDOR_B["phone"],
                queue_position=0,
                status="allocated",
                business_type=VENDOR_B["business_type"],
                preferred_zone=None,
                payment_method="airtel",
                applied_at=NOW - timedelta(days=40),
            )
        )

        for stand in (STAND_AVAILABLE, STAND_OCCUPIED, STAND_PAPER):
            conn.execute(insert(Stand).values(stand))

        conn.execute(
            insert(Application).values(
                id="app-mary-1",
                vendor_id=VENDOR_A_ID,
                stand_id=None,
                status="submitted",
                queue_position=0,
                business_type=VENDOR_A["business_type"],
                preferred_zone="Produce",
                created_at=NOW - timedelta(days=9),
            )
        )
        conn.execute(
            insert(Application).values(
                id="app-chanda-1",
                vendor_id=VENDOR_B_ID,
                stand_id=STAND_OCCUPIED["id"],
                status="allocated",
                queue_position=0,
                business_type=VENDOR_B["business_type"],
                preferred_zone=None,
                reviewed_by=ADMIN["id"],
                reviewed_at=NOW - timedelta(days=39),
                created_at=NOW - timedelta(days=40),
            )
        )

        conn.execute(
            insert(Allocation).values(
                id="alloc-chanda-1",
                application_id="app-chanda-1",
                stand_id=STAND_OCCUPIED["id"],
                vendor_id=VENDOR_B_ID,
                status="accepted",
                offered_by=ADMIN["id"],
                offered_at=NOW - timedelta(days=40),
                accepted_at=NOW - timedelta(days=39),
                fee_amount=Decimal("5.00"),
                currency="USD",
                permit_code="PAM-PERMIT-SEEDTEST01",
            )
        )
        conn.execute(
            insert(Payment).values(
                id="pay-chanda-1",
                allocation_id="alloc-chanda-1",
                vendor_id=VENDOR_B_ID,
                amount=Decimal("5.00"),
                currency="USD",
                status="successful",
                provider="devdraft",
                receipt_no="RCP-2201",
                idempotency_key="seed-idem-chanda-1",
                description="Stand levy ST-101",
                completed_at=NOW - timedelta(days=39),
            )
        )

        conn.execute(
            insert(Notification).values(
                id="notif-mary-1",
                user_id=VENDOR_A["id"],
                type="application_received",
                title="Application received",
                message="Your application is in the queue.",
                read=False,
                created_at=NOW - timedelta(days=9),
            )
        )
        conn.execute(
            insert(AuditLog).values(
                id="audit-alloc-1",
                action="ALLOCATION_OFFERED",
                actor=ADMIN["id"],
                actor_role="admin",
                entity_type="allocation",
                entity_id="alloc-chanda-1",
                details=f"Offered ST-101 to {VENDOR_B['full_name']}",
                recorded_at=NOW - timedelta(days=40),
                prev_hash=None,
                entry_hash="seed-non-chain-hash",
            )
        )
        conn.execute(
            insert(CorruptionReport).values(
                id="report-1",
                reference="CR-SEED-1",
                category="Bribery",
                description="Asked for money",
                location="Zone Produce",
                contact_email=None,
                created_at=NOW - timedelta(days=1),
            )
        )

    seed_engine.dispose()

    # The Flask app and the chatbot service share one SQLite file per test.
    monkeypatch.setenv("CHATBOT_DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CHATBOT_SECRET_KEY", "test-secret-chatbot")
    monkeypatch.delenv("CHATBOT_LLM_PROVIDER", raising=False)
    chatbot_db._SESSION_FACTORY = None

    return url


@pytest.fixture()
def client(market_db, monkeypatch):
    from app import create_app

    set_chatbot_service(None)
    application = create_app()
    application.config["TESTING"] = True
    application.config["RATELIMIT_ENABLED"] = False
    application.config["SQLALCHEMY_DATABASE_URI"] = market_db

    service = ChatbotService(
        llm_client=RuleBasedLLMClient(),
        session_rule=RateLimitRule("session_per_ip", 100, 3600),
        message_rule=RateLimitRule("messages_per_session", 100, 60),
    )
    set_chatbot_service(service)

    with application.test_client() as test_client:
        yield test_client

    set_chatbot_service(None)
    chatbot_db._SESSION_FACTORY = None


def session_bundle(client, identity=None):
    """Create a chat session; returns (session_id, token, response_data)."""
    payload = {"identity": identity} if identity else {}
    response = client.post("/api/v1/chatbot/sessions", json=payload)
    assert response.status_code == 200, response.get_json()
    data = response.get_json()
    return data["sessionId"], data["chatToken"], data


def send(client, session_id, token, content):
    return client.post(
        f"/api/v1/chatbot/sessions/{session_id}/messages",
        json={"content": content},
        headers={"Authorization": f"Bearer {token}"},
    )


VENDOR_A_PROFILE = {
    "phone": VENDOR_A["phone"],
    "fullName": VENDOR_A["full_name"],
    "role": "vendor",
    "nrc": VENDOR_A["nrc"],
    "businessType": VENDOR_A["business_type"],
}
VENDOR_B_PROFILE = {
    "phone": VENDOR_B["phone"],
    "fullName": VENDOR_B["full_name"],
    "role": "vendor",
    "nrc": VENDOR_B["nrc"],
}
ADMIN_PROFILE = {
    "phone": ADMIN["phone"],
    "fullName": ADMIN["full_name"],
    "role": "admin",
}
