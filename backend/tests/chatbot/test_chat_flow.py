"""End-to-end chat flow tests through the HTTP API (contract §4)."""

from tests.chatbot.conftest import (
    ADMIN_PROFILE,
    VENDOR_A_PROFILE,
    send,
    session_bundle,
)


def test_vendor_asks_own_application_status(client):
    session_id, token, _ = session_bundle(client, VENDOR_A_PROFILE)
    response = send(client, session_id, token, "What is the status of my stand application?")
    assert response.status_code == 200
    payload = response.get_json()

    assistant = payload["assistantMessage"]
    assert assistant["role"] == "assistant"
    assert assistant["meta"]["verified"] is True
    assert "get_my_application_status" in assistant["meta"]["toolsUsed"]
    assert "pending" in assistant["content"].lower()
    assert "12" in assistant["content"]  # queue position from her record
    # nothing from vendor B leaks into the answer
    assert "Chanda" not in assistant["content"]


def test_policy_question_is_explained_not_verified(client):
    session_id, token, _ = session_bundle(client, None)  # guest
    response = send(client, session_id, token, "How does stand allocation work?")
    assert response.status_code == 200
    assistant = response.get_json()["assistantMessage"]
    assert assistant["meta"]["verified"] is False  # explanation, not a DB lookup
    assert "allocation" in assistant["content"].lower()


def test_availability_question_hits_real_counts(client):
    session_id, token, _ = session_bundle(client, None)
    response = send(client, session_id, token, "Which stands are still available?")
    assistant = response.get_json()["assistantMessage"]
    assert assistant["meta"]["verified"] is True
    assert "1 available" in assistant["content"]  # ST-001 is the only available stand


def test_vendor_asking_suspicious_activity_hits_permission_wall(client):
    session_id, token, _ = session_bundle(client, VENDOR_A_PROFILE)
    response = send(client, session_id, token, "Are there any suspicious allocations in the market?")
    assistant = response.get_json()["assistantMessage"]
    assert assistant["meta"]["verified"] is False
    assert "administrator" in assistant["content"].lower()
    assert "Paper" not in assistant["content"]  # no finding details leak


def test_admin_statistics_flow(client):
    session_id, token, _ = session_bundle(client, ADMIN_PROFILE)
    response = send(client, session_id, token, "How many applications are pending?")
    assistant = response.get_json()["assistantMessage"]
    assert assistant["meta"]["verified"] is True
    assert "get_application_statistics" in assistant["meta"]["toolsUsed"]
    assert "pending 1" in assistant["content"].lower()


def test_history_matches_transcript(client):
    session_id, token, _ = session_bundle(client, VENDOR_A_PROFILE)
    send(client, session_id, token, "What is the status of my stand application?")
    history = client.get(
        f"/api/v1/chatbot/sessions/{session_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    messages = history.get_json()["messages"]
    roles = [m["role"] for m in messages]
    assert roles.count("tool") == 0  # tool turns stay in the audit store
    assistant_rows = [m for m in messages if m["role"] == "assistant"]
    assert any(m["meta"].get("verified") for m in assistant_rows)


def test_cross_session_read_is_denied(client):
    session_a, token_a, _ = session_bundle(client, VENDOR_A_PROFILE)
    session_b, token_b, _ = session_bundle(client, ADMIN_PROFILE)

    # A cannot read B's transcript with A's own token
    foreign = client.get(
        f"/api/v1/chatbot/sessions/{session_b}/messages",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert foreign.status_code == 404
    assert foreign.get_json()["error"]["code"] == "session_not_found"

    # unknown session ids look the same as foreign sessions
    unknown = client.get(
        "/api/v1/chatbot/sessions/does-not-exist/messages",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert unknown.status_code == 404


def test_rate_limited_messages(client):
    from app.chatbot.ratelimit import RateLimitRule
    from app.extensions import set_chatbot_service
    from app.chatbot import ChatbotService
    from app.chatbot.llm import RuleBasedLLMClient

    session_id, token, _ = session_bundle(client, VENDOR_A_PROFILE)

    tight = ChatbotService(
        llm_client=RuleBasedLLMClient(),
        session_rule=RateLimitRule("s", 1000, 3600),
        message_rule=RateLimitRule("m", 2, 60),
    )
    set_chatbot_service(tight)
    try:
        assert send(client, session_id, token, "hello one").status_code == 200
        assert send(client, session_id, token, "hello two").status_code == 200
        third = send(client, session_id, token, "hello three")
        assert third.status_code == 429
        assert third.get_json()["error"]["code"] == "rate_limited"
    finally:
        set_chatbot_service(None)
