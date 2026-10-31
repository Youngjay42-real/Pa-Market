"""Shared pytest fixtures for chatbot tests.

Builds an isolated SQLite database that mirrors the Prisma schema (same table and
column names), seeds representative records, boots the Flask app with the mock LLM
and generous rate limits, and returns a test client.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
for candidate in (str(BACKEND_DIR), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from sqlalchemy import insert  # noqa: E402

from app import config as app_config  # noqa: F401,E402  (loaded for parity with runtime)
from app.chatbot import ChatbotService  # noqa: E402
from app.chatbot import database as chatbot_db  # noqa: E402
from app.chatbot import data_models as legacy  # noqa: E402
from app.chatbot.database import make_engine  # noqa: E402
from app.chatbot.llm import RuleBasedLLMClient  # noqa: E402
from app.chatbot.models import Base as ChatBase  # noqa: E402
from app.chatbot.ratelimit import RateLimitRule  # noqa: E402
from app.extensions import set_chatbot_service  # noqa: E402

NOW = datetime.now(timezone.utc)

VENDOR_A = {  # "Mary Banda" — has a pending application
    "id": "user-mary",
    "phone": "0977123456",
    "fullName": "Mary Banda",
    "password": "pass123",
    "role": "vendor",
    "nrc": "123456/78/1",
    "businessType": "Vegetables",
    "createdAt": NOW - timedelta(days=9),
}
VENDOR_B = {  # second vendor — allocated to a stand
    "id": "user-chanda",
    "phone": "0966444777",
    "fullName": "Chanda Mwansa",
    "password": "secret7",
    "role": "vendor",
    "nrc": "999111/22/3",
    "businessType": "Fish/Meat",
    "createdAt": NOW - timedelta(days=40),
}
ADMIN = {
    "id": "user-admin",
    "phone": "0776596009",
    "fullName": "Council Administrator",
    "password": "1234567",
    "role": "admin",
    "nrc": None,
    "businessType": None,
    "createdAt": NOW - timedelta(days=200),
}

STAND_AVAILABLE = {
    "id": "ST-001", "row": 0, "col": 1, "zone": "Produce", "status": "available",
    "vendorName": None, "vendorNrc": None, "allocatedAt": None, "holdExpiresAt": None,
}
STAND_OCCUPIED = {
    "id": "ST-101", "row": 2, "col": 4, "zone": "Textiles", "status": "occupied",
    "vendorName": "Chanda Mwansa", "vendorNrc": "999111/22/3", "allocatedAt": NOW - timedelta(days=40),
    "holdExpiresAt": None,
}
STAND_PAPER = {  # occupied long ago without any confirmed payment → paper-occupied flag
    "id": "ST-102", "row": 2, "col": 5, "zone": "Textiles", "status": "occupied",
    "vendorName": "Paper Holder", "vendorNrc": "888222/55/1", "allocatedAt": NOW - timedelta(days=75),
    "holdExpiresAt": None,
}


@pytest.fixture()
def market_db(tmp_path, monkeypatch):
    """Create + seed a throwaway database that mirrors the app schema."""
    db_path = tmp_path / "market_seed.sqlite3"
    url = f"sqlite:///{db_path}"

    seed_engine = make_engine(url)
    legacy.legacy_metadata.create_all(seed_engine)
    ChatBase.metadata.create_all(seed_engine)

    with seed_engine.begin() as conn:
        for user in (VENDOR_A, VENDOR_B, ADMIN):
            conn.execute(insert(legacy.User).values(user))

        # Vendor === application record in the current schema
        conn.execute(
            insert(legacy.Vendor).values(
                nrc=VENDOR_A["nrc"], fullName=VENDOR_A["fullName"], phone=VENDOR_A["phone"],
                queuePosition=12, status="pending", standId=None,
                businessType=VENDOR_A["businessType"], preferredZone="Produce",
                paymentMethod="MTN MoMo", appliedAt=NOW - timedelta(days=9),
            )
        )
        conn.execute(
            insert(legacy.Vendor).values(
                nrc=VENDOR_B["nrc"], fullName=VENDOR_B["fullName"], phone=VENDOR_B["phone"],
                queuePosition=0, status="allocated", standId=STAND_OCCUPIED["id"],
                businessType=VENDOR_B["businessType"], preferredZone=None,
                paymentMethod="Airtel Money", appliedAt=NOW - timedelta(days=40),
            )
        )

        for stand in (STAND_AVAILABLE, STAND_OCCUPIED, STAND_PAPER):
            conn.execute(insert(legacy.Stand).values(stand))

        conn.execute(
            insert(legacy.Payment).values(
                id="PAY-M-001", vendorNrc=VENDOR_A["nrc"], amount=350.0,
                currency="ZMW", status="pending", method="MTN MoMo", receiptNo=None,
                createdAt=NOW - timedelta(days=2),
            )
        )
        conn.execute(
            insert(legacy.Payment).values(
                id="PAY-B-001", vendorNrc=VENDOR_B["nrc"], amount=350.0,
                currency="ZMW", status="confirmed", method="Airtel Money",
                receiptNo="RCP-2201", createdAt=NOW - timedelta(days=39),
            )
        )

        conn.execute(
            insert(legacy.Notification).values(
                id="N-1", vendorNrc=VENDOR_A["nrc"], type="application_received",
                title="Application received", message="Your application is in the queue.",
                receiptJson=None, read=False, createdAt=NOW - timedelta(days=9),
            )
        )
        conn.execute(
            insert(legacy.AuditLog).values(
                id="AUD-ALLOC-1", action="STAND_ALLOCATED", actor="admin@lusaka.gov.zm",
                entityType="stand", entityId=STAND_OCCUPIED["id"],
                details=f"Allocated to {VENDOR_B['fullName']}",
                timestamp=NOW - timedelta(days=40),
            )
        )
        conn.execute(
            insert(legacy.Report).values(
                id="REP-1", category="Bribery", description="Asked for money",
                location="Zone Produce", contactEmail=None, createdAt=NOW - timedelta(days=1),
            )
        )
        conn.execute(
            insert(legacy.DailySale).values(
                id="DS-1", vendorNrc=VENDOR_A["nrc"], amount=250.0, taxAmount=25.0,
                date=NOW - timedelta(days=1), status="unpaid",
            )
        )
        conn.execute(
            insert(legacy.TaxPayment).values(
                id="TP-1", vendorNrc=VENDOR_A["nrc"], amount=40.0,
                paidAt=NOW - timedelta(days=5), receiptNo="TR-8812",
            )
        )
        conn.execute(
            insert(legacy.VillageBankingAccount).values(
                id="VB-1", vendorNrc=VENDOR_A["nrc"], groupId="Group A",
                balance=1250.0, savingsGoal=5000.0, interestRate=0.05,
                createdAt=NOW - timedelta(days=30),
            )
        )

    seed_engine.dispose()

    monkeypatch.setenv("CHATBOT_DATABASE_URL", url)
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
    """Create a chat session; returns (session_id, token)."""
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
    "fullName": VENDOR_A["fullName"],
    "role": "vendor",
    "nrc": VENDOR_A["nrc"],
    "businessType": VENDOR_A["businessType"],
}
VENDOR_B_PROFILE = {
    "phone": VENDOR_B["phone"],
    "fullName": VENDOR_B["fullName"],
    "role": "vendor",
    "nrc": VENDOR_B["nrc"],
}
ADMIN_PROFILE = {
    "phone": ADMIN["phone"],
    "fullName": ADMIN["fullName"],
    "role": "admin",
}
