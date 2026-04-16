import json
import pytest


class TestPrivacyExport:
    def test_export_json(self, client, auth_headers):
        resp = client.get("/privacy/export", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "profile" in data
        assert "expenses" in data
        assert "categories" in data
        assert "bills" in data
        assert "reminders" in data
        assert "export_metadata" in data
        assert data["export_metadata"]["gdpr_article"] == "Article 20 - Right to data portability"

    def test_export_csv(self, client, auth_headers):
        resp = client.get("/privacy/export?format=csv", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert "Section,Field,Value" in resp.get_data(as_text=True)

    def test_export_requires_auth(self, client):
        resp = client.get("/privacy/export")
        assert resp.status_code == 401


class TestPrivacyDelete:
    def test_delete_requires_confirmation(self, client, auth_headers):
        resp = client.post(
            "/privacy/delete",
            headers=auth_headers,
            json={"confirm": "WRONG"},
        )
        assert resp.status_code == 400

    def test_delete_account(self, client, auth_headers):
        resp = client.post(
            "/privacy/delete",
            headers=auth_headers,
            json={"confirm": "DELETE"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "deleted"

    def test_delete_requires_auth(self, client):
        resp = client.post("/privacy/delete", json={"confirm": "DELETE"})
        assert resp.status_code == 401
