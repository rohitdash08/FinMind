from app.extensions import db
from app.models import AuditLog, User


def test_export_personal_data_package(client, auth_header):
    client.post(
        "/categories",
        json={"name": "Food"},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 12.5, "description": "Lunch", "date": "2026-04-01"},
        headers=auth_header,
    )
    client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 50,
            "next_due_date": "2026-05-01",
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )

    response = client.get("/privacy/export", headers=auth_header)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["user"]["email"] == "test@example.com"
    assert payload["categories"][0]["name"] == "Food"
    assert payload["expenses"][0]["description"] == "Lunch"
    assert payload["bills"][0]["name"] == "Internet"
    assert payload["audit_logs"]


def test_delete_requires_confirmation(client, auth_header):
    response = client.delete("/privacy/delete", json={}, headers=auth_header)

    assert response.status_code == 400
    assert response.get_json()["error"] == 'confirmation must equal "DELETE"'


def test_delete_personal_data_is_irreversible_and_audited(client, auth_header, app_fixture):
    client.post(
        "/expenses",
        json={"amount": 25, "description": "Taxi", "date": "2026-04-02"},
        headers=auth_header,
    )

    response = client.delete(
        "/privacy/delete",
        json={"confirmation": "DELETE"},
        headers=auth_header,
    )

    assert response.status_code == 200
    with app_fixture.app_context():
        assert db.session.query(User).filter_by(email="test@example.com").first() is None
        audit = db.session.query(AuditLog).filter(
            AuditLog.action.like("privacy.delete_completed:%")
        ).first()
        assert audit is not None
        assert audit.user_id is None
