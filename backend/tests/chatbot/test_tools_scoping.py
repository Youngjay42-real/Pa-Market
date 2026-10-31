"""Permission scoping tests — the core security property (contract §1/§2).

A vendor can only ever read their own records; guests get nothing personal; admins
are the only role allowed market-wide tools. Scoping keys never come from the
request payload.
"""

import pytest

from app.chatbot import gateway
from app.chatbot.database import session_scope
from app.chatbot.identity import verify_identity
from app.chatbot.permissions import AccessContext, PermissionDenied
from app.chatbot.tools import execute_tool
from tests.conftest import ADMIN_PROFILE, VENDOR_A_PROFILE, VENDOR_B_PROFILE


@pytest.fixture()
def contexts(market_db):
    """Yield access contexts for vendor A, vendor B and the admin."""

    def context_for(profile):
        with session_scope() as session:
            identity, error = verify_identity(session, profile)
            assert error is None
            assert identity is not None
        return identity

    return {
        "vendor_a": context_for(VENDOR_A_PROFILE),
        "vendor_b": context_for(VENDOR_B_PROFILE),
        "admin": context_for(ADMIN_PROFILE),
    }


def _ctx(contexts, key):
    with session_scope() as session:
        return AccessContext(identity=contexts[key], session=session)


def test_vendor_a_sees_only_own_application(contexts):
    ctx = _ctx(contexts, "vendor_a")
    result = gateway.my_application(ctx)
    assert result["ok"] is True
    app = result["application"]
    assert app["status"] == "pending"
    assert app["queuePosition"] == 12


def test_vendor_b_sees_only_own_application(contexts):
    ctx = _ctx(contexts, "vendor_b")
    result = gateway.my_application(ctx)
    assert result["application"]["status"] == "allocated"
    assert result["stand"]["id"] == "ST-101"
    # no leak of vendor A anywhere in the payload
    assert "Mary" not in str(result)


def test_guest_denied_personal_tools(contexts):
    with session_scope() as session:
        from app.chatbot.identity import guest_id

        ctx = AccessContext(identity=guest_id(), session=session)
        outcome = execute_tool(ctx, "get_my_application_status", {})
        assert outcome["ok"] is False and outcome["denied"] is True
        outcome = execute_tool(ctx, "get_my_payments", {})
        assert outcome["denied"] is True


def test_vendor_denied_admin_tools(contexts):
    ctx = _ctx(contexts, "vendor_a")
    outcome = execute_tool(ctx, "find_suspicious_activity", {})
    assert outcome["ok"] is False and outcome["denied"] is True
    assert "administrator" in outcome["error"].lower()

    outcome = execute_tool(ctx, "get_queue_summary", {})
    assert outcome["denied"] is True


def test_admin_receives_market_data_without_personal_phones(contexts):
    ctx = _ctx(contexts, "admin")
    queue = gateway.queue_summary(ctx)
    assert queue["ok"] is True and queue["queueDepth"] == 1
    assert "0977123456" not in str(queue)  # phone numbers are never exposed, even to admins

    flags = gateway.suspicious_activity(ctx)
    assert flags["ok"] is True
    assert any(f["pattern"] == "paper_occupied_stand" for f in flags["findings"])


def test_unknown_tool_is_structural_no_crash(contexts):
    ctx = _ctx(contexts, "admin")
    outcome = execute_tool(ctx, "make_me_a_millionaire", {})
    assert outcome["ok"] is False
