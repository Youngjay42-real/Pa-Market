"""Identity verification tests (CHATBOT_CONTRACT.md §3)."""

from tests.conftest import (
    ADMIN_PROFILE,
    VENDOR_A_PROFILE,
    VENDOR_B_PROFILE,
    session_bundle,
)

GENERIC = "identity_invalid"


def test_verified_vendor_session(client):
    session_id, token, data = session_bundle(client, VENDOR_A_PROFILE)
    assert session_id and token
    assert data["identity"] == {"kind": "verified", "role": "vendor", "displayName": "Mary Banda"}
    assert "Mary" in data["greeting"]
    assert data["suggestedPrompts"]


def test_guest_session_by_default(client):
    session_id, token, data = session_bundle(client, None)
    assert data["identity"]["kind"] == "guest"
    assert data["identity"]["role"] == "guest"


def test_wrong_name_is_rejected_with_generic_error(client):
    bad = dict(VENDOR_A_PROFILE, fullName="Someone Else")
    response = client.post("/api/v1/chatbot/sessions", json={"identity": bad})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == GENERIC


def test_role_lies_are_rejected(client):
    # a vendor cannot pose as an administrator
    impostor = dict(VENDOR_A_PROFILE, role="admin")
    response = client.post("/api/v1/chatbot/sessions", json={"identity": impostor})
    assert response.status_code == 401

    # an admin cannot pose as a vendor/with someone else's nrc
    response = client.post("/api/v1/chatbot/sessions", json={"identity": dict(ADMIN_PROFILE, nrc=VENDOR_A_PROFILE["nrc"])})
    assert response.status_code == 401


def test_phone_only_identity_is_rejected(client):
    response = client.post("/api/v1/chatbot/sessions", json={"identity": {"phone": VENDOR_B_PROFILE["phone"]}})
    assert response.status_code == 200  # half profiles degrade to guest sessions
    assert response.get_json()["identity"]["kind"] == "guest"


def test_tampered_tokens_are_rejected(client):
    session_id, token, _ = session_bundle(client, VENDOR_A_PROFILE)
    response = client.post(
        f"/api/v1/chatbot/sessions/{session_id}/messages",
        json={"content": "hello"},
        headers={"Authorization": f"Bearer not-a-real-token"},
    )
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "chat_token_invalid"
