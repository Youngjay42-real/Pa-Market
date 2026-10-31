"""Allocation lifecycle: offer → accept → handover (both parties) → eligibility."""
import pytest


@pytest.fixture()
def approved_application(client, admin_token, vendor_token, stands):
    submit = client.post(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {vendor_token}"},
        json={"business_type": "Food & Fresh Produce", "preferred_zone": "Produce"},
    )
    application_id = submit.get_json()["id"]
    client.post(
        f"/api/v1/applications/{application_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"decision": "approved"},
    )
    return application_id


def test_admin_auto_assigns_matching_stand(client, app, admin_token, approved_application):
    auth_a = {"Authorization": f"Bearer {admin_token}"}
    # conftest `stands` fixture provided: ST-101 Textiles, ST-102 Hardware,
    # ST-103 Food Court, ST-104.. ST-1xx Produce (10 stands).

    response = client.post("/api/v1/allocations", headers=auth_a, json={"application_id": approved_application, "auto_assign": True})
    assert response.status_code == 201
    payload = response.get_json()
    # Produce suits "Food & Fresh Produce" *and* the preferred zone — it wins on 30 pts.
    assert payload["stand"]["zone"] == "Produce"
    assert payload["status"] == "offered"

    from app.extensions import db
    from app.models import Stand

    with app.app_context():
        stand = db.session.get(Stand, payload["stand"]["id"])
        assert stand.status == "reserved"


def test_vendor_accepts_then_both_handovers_unlock_payment(client, admin_token, vendor_token, approved_application):
    auth_v = {"Authorization": f"Bearer {vendor_token}"}
    auth_a = {"Authorization": f"Bearer {admin_token}"}

    allocate = client.post(
        "/api/v1/allocations", headers=auth_a,
        json={"application_id": approved_application, "auto_assign": True},
    ).get_json()
    allocation_id = allocate["id"]

    # Vendor sees it in /mine and accepts
    mine = client.get("/api/v1/allocations/mine", headers=auth_v).get_json()
    assert mine["allocations"][0]["id"] == allocation_id
    accepted = client.post(f"/api/v1/allocations/{allocation_id}/accept", headers=auth_v)
    assert accepted.get_json()["status"] == "accepted"

    # Eligibility must fail before handover
    early = client.get(f"/api/v1/allocations/{allocation_id}/eligibility", headers=auth_v).get_json()
    assert early["eligible"] is False
    assert any("handover" in r for r in early["reasons"])

    # Vendor confirms first (partial), then official confirms (complete)
    vendor_confirm = client.post(
        f"/api/v1/allocations/{allocation_id}/handover", headers=auth_v,
        json={"meeting_location": "Gate 3"},
    )
    assert vendor_confirm.get_json()["status"] == "accepted"

    official_confirm = client.post(
        f"/api/v1/allocations/{allocation_id}/handover", headers=auth_a, json={}
    )
    assert official_confirm.get_json()["status"] == "handover_confirmed"

    eligibility = client.get(
        f"/api/v1/allocations/{allocation_id}/eligibility", headers=auth_v
    ).get_json()
    assert eligibility["eligible"] is True, eligibility


def test_vendor_cannot_confirm_handover_for_someone_else(client, admin_token, vendor_token, approved_application):
    auth_a = {"Authorization": f"Bearer {admin_token}"}
    allocate = client.post(
        "/api/v1/allocations", headers=auth_a,
        json={"application_id": approved_application, "auto_assign": True},
    ).get_json()
    allocation_id = allocate["id"]

    # another vendor account
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "phone": "0968112233", "full_name": "Other Vendor", "password": "strongpass",
            "nrc": "999999/11/2", "business_type": "Food & Fresh Produce",
        },
    )
    other_token = signup.get_json()["token"]

    accepted = client.post(
        f"/api/v1/allocations/{allocation_id}/accept",
        headers={"Authorization": f"Bearer {vendor_token}"},
    )
    assert accepted.status_code == 200

    poacher = client.post(
        f"/api/v1/allocations/{allocation_id}/handover",
        headers={"Authorization": f"Bearer {other_token}"}, json={},
    )
    assert poacher.status_code == 403
