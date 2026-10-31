"""Payments: eligibility gating, idempotency, limits, webhooks, refunds."""
import hashlib
import hmac as hmac_mod
import pytest

from app.extensions import db
from app.models import Payment

from .conftest import h

WEBHOOK_SECRET = "test-webhook-signing-secret"


@pytest.fixture()
def payable_allocation(client, admin_token, vendor_token, stands):
    auth_a = {"Authorization": f"Bearer {admin_token}"}
    auth_v = {"Authorization": f"Bearer {vendor_token}"}

    submit = client.post(
        "/api/v1/applications", headers=auth_v,
        json={"business_type": "Food & Fresh Produce", "preferred_zone": "Produce"},
    )
    application_id = submit.get_json()["id"]
    client.post(
        f"/api/v1/applications/{application_id}/review", headers=auth_a,
        json={"decision": "approved"},
    )
    allocate = client.post(
        "/api/v1/allocations", headers=auth_a, json={"application_id": application_id, "auto_assign": True}
    ).get_json()
    allocation_id = allocate["id"]
    client.post(f"/api/v1/allocations/{allocation_id}/accept", headers=auth_v)
    client.post(f"/api/v1/allocations/{allocation_id}/handover", headers=auth_v, json={})
    client.post(f"/api/v1/allocations/{allocation_id}/handover", headers=auth_a, json={})
    return allocation_id


def _initiate(client, token, allocation_id, key="itest-pay-0001", amount=None):
    import json

    body = {"allocation_id": allocation_id}
    if amount:
        body["amount"] = amount
    response = client.post(
        "/api/v1/payments/initiate", headers={**h(token), "Idempotency-Key": key}, json=body
    )
    return response


def test_payment_requires_idempotency_key(client, admin_token, payable_allocation):
    response = client.post(
        "/api/v1/payments/initiate",
        headers=h(admin_token),
        json={"allocation_id": payable_allocation},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "idempotency_key_required"


def test_successful_sandbox_payment_issues_receipt_and_permit(client, vendor_token, admin_token, payable_allocation):
    auth_v = h(vendor_token)
    response = _initiate(client, vendor_token, payable_allocation)
    assert response.status_code == 201, response.get_json()
    payment = response.get_json()
    assert payment["status"] == "successful"  # sandbox resolves synchronously
    assert payment["provider"] == "devdraft-sandbox"
    payment_id = payment["id"]

    status = client.get(f"/api/v1/payments/{payment_id}/status", headers=auth_v).get_json()
    assert status["status"] == "successful"

    receipt = client.get(f"/api/v1/payments/{payment_id}/receipt", headers=auth_v)
    assert receipt.status_code == 200
    payload = receipt.get_json()
    assert payload["receipt_no"].startswith("PAM-")
    assert payload["permit_code"]
    assert any(e["signature_valid"] is None for e in payload["events"])

    permit = client.get(
        f"/api/v1/allocations/{payable_allocation}/permit", headers=auth_v
    ).get_json()
    assert permit["permit_code"] == payload["permit_code"]

    # idempotent replay returns the same payment, not a second charge
    replay = _initiate(client, vendor_token, payable_allocation, key="itest-pay-0001")
    assert replay.get_json()["id"] == payment_id


def test_payment_blocked_until_handover(client, vendor_token, admin_token, app, stands):
    auth_a = {"Authorization": f"Bearer {admin_token}"}
    auth_v = h(vendor_token)
    submit = client.post(
        "/api/v1/applications", headers=auth_v,
        json={"business_type": "Food & Fresh Produce"},
    )
    application_id = submit.get_json()["id"]
    client.post(f"/api/v1/applications/{application_id}/review", headers=auth_a, json={"decision": "approved"})
    allocation_id = client.post(
        "/api/v1/allocations", headers=auth_a, json={"application_id": application_id, "auto_assign": True}
    ).get_json()["id"]
    client.post(f"/api/v1/allocations/{allocation_id}/accept", headers=h(vendor_token))

    response = _initiate(client, vendor_token, allocation_id)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "payment_not_eligible"
    assert any("handover" in r for r in response.get_json()["error"]["details"]["reasons"])


def test_signed_webhook_confirms_payment_exactly_once(client, app, vendor_token, payable_allocation):
    auth_v = h(vendor_token)
    response = _initiate(client, vendor_token, payable_allocation)  # sandbox: succeeded at once
    payment_id = response.get_json()["id"]
    provider_reference = response.get_json()["provider_reference"]

    raw_body = (
        b'{"id": "evt_1", "type": "payment.completed", "created": "2026-10-31T09:00:00Z",'
        b' "data": {"object": {"id": "%s", "status": "succeeded", "amount": 5.0}}}' % provider_reference.encode()
    )
    signature = hmac_mod.new(WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()

    first = client.post(
        "/api/v1/payments/webhook/devdraft",
        data=raw_body, content_type="application/json",
        headers={"x-webhook-signature": f"sha256={signature}"},
    )
    assert first.status_code == 200, first.get_json()

    replay = client.post(
        "/api/v1/payments/webhook/devdraft",
        data=raw_body, content_type="application/json",
        headers={"x-webhook-signature": signature},
    )
    assert replay.get_json()["action"] == "duplicate_ignored"

    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        events = [e.event_type for e in payment.events]
        assert events.count("webhook:payment.completed") == 1

    body = client.get(f"/api/v1/payments/{payment_id}/receipt", headers=auth_v).get_json()
    assert body["status"] == "successful"


def test_webhook_rejects_bad_signature(client):
    response = client.post(
        "/api/v1/payments/webhook/devdraft",
        data=b'{"id": "evt_x", "type": "payment.completed", "data": {"object": {}}}',
        content_type="application/json",
        headers={"x-webhook-signature": "deadbeef"},
    )
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_webhook_signature"


def test_per_transaction_limit_enforced(client, app, admin_token, vendor_token, payable_allocation):
    from decimal import Decimal

    from app.models import Allocation

    with app.app_context():
        allocation = db.session.get(Allocation, payable_allocation)
        allocation.fee_amount = Decimal("9.99")  # above the $5 cap
        db.session.commit()

    response = _initiate(client, vendor_token, payable_allocation)
    assert response.status_code == 409
    payload = response.get_json()["error"]
    assert payload["code"] == "payment_not_eligible"
    assert any("limit" in r for r in payload["details"]["reasons"])


def test_team_total_limit_enforced(client, app, admin_token, vendor_token, stands):
    auth_a = {"Authorization": f"Bearer {admin_token}"}
    auth_v = h(vendor_token)

    for attempt in range(11):  # 10 × $5 = $50 cap; the 11th must be blocked
        submit = client.post(
            "/api/v1/applications", headers=auth_v,
            json={"business_type": "Food & Fresh Produce"},
        )
        application_id = submit.get_json()["id"]
        client.post(
            f"/api/v1/applications/{application_id}/review", headers=auth_a, json={"decision": "approved"}
        )
        allocation_id = client.post(
            "/api/v1/allocations", headers=auth_a, json={"application_id": application_id, "auto_assign": True}
        ).get_json()["id"]
        client.post(f"/api/v1/allocations/{allocation_id}/accept", headers=auth_v)
        client.post(f"/api/v1/allocations/{allocation_id}/handover", headers=auth_v, json={})
        client.post(f"/api/v1/allocations/{allocation_id}/handover", headers=auth_a, json={})

        response = _initiate(client, vendor_token, allocation_id, key=f"vol-pay-{attempt:04d}")
        if attempt < 10:
            assert response.status_code == 201, response.get_json()
        else:
            assert response.status_code == 409
            reasons = response.get_json()["error"]["details"]["reasons"]
            assert any("volume" in r for r in reasons)

    limits = client.get("/api/v1/payments/team/limits", headers=auth_a).get_json()
    assert limits["spent_so_far"] == "50.00"
    assert limits["remaining"] == "0.00"


def test_admin_refunds_successful_payment(client, app, vendor_token, admin_token, payable_allocation):
    auth_a = {"Authorization": f"Bearer {admin_token}"}
    response = _initiate(client, vendor_token, payable_allocation)
    payment_id = response.get_json()["id"]

    from app.models import Allocation

    with app.app_context():
        allocation = db.session.get(Allocation, payable_allocation)
        assert allocation.status == "completed"
        permit_code = allocation.permit_code
        assert permit_code

    refund = client.post(f"/api/v1/payments/{payment_id}/refund", headers=auth_a, json={"reason": "test cleanup"})
    assert refund.get_json()["status"] == "refunded"

    with app.app_context():
        allocation = db.session.get(Allocation, payable_allocation)
        assert allocation.status == "cancelled"
        assert allocation.permit_code is None
        stand = allocation.stand
        assert stand.status == "available"
        assert stand.vendor_name is None
