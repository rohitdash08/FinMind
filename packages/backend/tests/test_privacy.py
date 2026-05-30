import json
import zipfile
import io
from app.extensions import db
from app.models import AuditLog


def _create_expense(client, auth_header, amount=10.0, description="Coffee", exp_date="2026-02-12"):
    r = client.post(
        "/expenses",
        json={"amount": amount, "description": description, "date": exp_date},
        headers=auth_header,
    )
    assert r.status_code == 201


def _create_bill(client, auth_header, name="Electric", amount=100.0, due_date="2026-03-01"):
    r = client.post(
        "/bills",
        json={"name": name, "amount": amount, "next_due_date": due_date, "cadence": "MONTHLY"},
        headers=auth_header,
    )
    assert r.status_code == 201


def test_export_returns_zip_with_all_user_data(client, auth_header):
    _create_expense(client, auth_header)
    _create_bill(client, auth_header)

    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 200
    assert r.content_type == "application/zip"

    buf = io.BytesIO(r.data)
    with zipfile.ZipFile(buf, "r") as zf:
        names = zf.namelist()
        assert "profile.json" in names
        assert "expenses.json" in names
        assert "bills.json" in names
        assert "categories.json" in names
        assert "reminders.json" in names
        assert "recurring_expenses.json" in names
        assert "audit_log.json" in names
        assert "manifest.json" in names

        profile = json.loads(zf.read("profile.json"))
        assert "id" in profile
        assert "email" in profile

        expenses = json.loads(zf.read("expenses.json"))
        assert len(expenses) >= 1

        bills = json.loads(zf.read("bills.json"))
        assert len(bills) >= 1

        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["schema_version"] == "1.0"
        assert "counts" in manifest


def test_delete_requires_confirmation(client, auth_header):
    r = client.delete("/privacy/delete", json={}, headers=auth_header)
    assert r.status_code == 400

    r = client.delete("/privacy/delete", json={"confirmation": "WRONG"}, headers=auth_header)
    assert r.status_code == 400


def test_delete_removes_all_user_data(client, auth_header):
    _create_expense(client, auth_header, amount=50.0, description="To be deleted")
    _create_bill(client, auth_header, name="To be deleted bill")

    r = client.get("/expenses", headers=auth_header)
    assert len(r.get_json()) >= 1

    r = client.delete("/privacy/delete", json={"confirmation": "DELETE_MY_DATA"}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "all user data permanently deleted"

    r = client.get("/auth/me", headers=auth_header)
    assert r.status_code in (401, 404)


def test_audit_log_tracks_privacy_actions(client, auth_header):
    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/privacy/audit-log", headers=auth_header)
    assert r.status_code == 200
    logs = r.get_json()
    actions = [l["action"] for l in logs]
    assert "DATA_EXPORT_REQUESTED" in actions
    assert "DATA_EXPORT_COMPLETED" in actions


def test_audit_log_tracks_deletion(client, auth_header, app_fixture):
    _create_expense(client, auth_header)

    r = client.delete("/privacy/delete", json={"confirmation": "DELETE_MY_DATA"}, headers=auth_header)
    assert r.status_code == 200

    with app_fixture.app_context():
        audit_logs = (
            db.session.query(AuditLog)
            .filter_by(action="DATA_DELETION_COMPLETED")
            .all()
        )
        assert len(audit_logs) >= 1
