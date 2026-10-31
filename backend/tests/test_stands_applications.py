"""Stands and vendor application queue behaviour."""
from app.extensions import db
from app.models import Stand

from .conftest import h


def test_stands_are_public(client):
    response = client.get("/api/v1/stands")
    assert response.status_code == 200


def test_stand_filters_and_meta(client, app):
    with app.app_context():
        db.session.add(Stand(code="ST-001", row=0, col=0, zone="Produce", status="available"))
        db.session.add(Stand(code="ST-002", row=0, col=1, zone="Produce", status="occupied"))
        db.session.add(Stand(code="ST-003", row=1, col=0, zone="Textiles", status="maintenance"))
        db.session.commit()

    response = client.get("/api/v1/stands?zone=Produce&status=occupied")
    payload = response.get_json()
    assert [s["code"] for s in payload["stands"]] == ["ST-002"]

    response = client.get("/api/v1/stands/stats")
    zones = {z["zone"]: z["counts"] for z in response.get_json()["zones"]}
    assert zones["Produce"]["available"] == 1
    assert zones["Textiles"]["maintenance"] == 1

    response = client.get("/api/v1/stands/meta")
    meta = response.get_json()
    assert "Food & Fresh Produce" in meta["business_categories"]
    assert meta["category_zones"]["Food & Fresh Produce"] == ["Produce", "Food Court"]


def test_vendor_submits_application(client, vendor_token):
    response = client.post(
        "/api/v1/applications",
        headers=h(vendor_token),
        json={"business_type": "Food & Fresh Produce", "preferred_zone": "Produce", "notes": "Tomatoes"},
    )
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["status"] == "submitted"
    assert payload["queue_position"] == 1

    duplicate = client.post(
        "/api/v1/applications",
        headers=h(vendor_token),
        json={"business_type": "Food & Fresh Produce"},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "application_exists"


def test_admin_sees_queue_with_vendor_info_moves_with_review(client, vendor_token, admin_token):
    client.post(
        "/api/v1/applications",
        headers=h(vendor_token),
        json={"business_type": "Tailoring & Textiles", "preferred_zone": "Textiles"},
    )
    response = client.get("/api/v1/applications", headers=h(admin_token))
    assert response.status_code == 200
    payload = response.get_json()["applications"][0]
    assert payload["vendor"]["nrc"] == "123456/78/1"
    application_id = payload["id"]

    approve = client.post(
        f"/api/v1/applications/{application_id}/review",
        headers=h(admin_token),
        json={"decision": "approved"},
    )
    assert approve.get_json()["status"] == "approved"

    mine = client.get("/api/v1/applications/mine", headers=h(vendor_token)).get_json()
    assert mine["applications"][0]["status"] == "approved"
