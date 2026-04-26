"""Tests for smart reminder timing (#111) and merchant alias management (#114)."""

from datetime import date, datetime, timedelta


# ---------------------------------------------------------------------------
# Smart reminder timing (#111)
# ---------------------------------------------------------------------------

class TestReminderTiming:
    def test_returns_defaults_with_no_history(self, client, auth_header):
        r = client.get("/insights/reminder-timing", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "recommended_hour" in data
        assert "recommended_days_before_due" in data
        assert "recommended_weekday" in data
        assert "confidence" in data
        assert data["confidence"] == "low"
        # Default hour should be 9
        assert data["recommended_hour"] == 9

    def test_suggested_send_at_with_due_date(self, client, auth_header):
        future_date = (date.today() + timedelta(days=14)).isoformat()
        r = client.get(
            f"/insights/reminder-timing?due_date={future_date}",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert "suggested_send_at" in data
        assert "bill_due_date" in data
        assert data["bill_due_date"] == future_date

        # suggested_send_at must be before the due date
        send_at = datetime.fromisoformat(data["suggested_send_at"]).date()
        due = date.fromisoformat(future_date)
        assert send_at < due

    def test_requires_auth(self, client):
        r = client.get("/insights/reminder-timing")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Merchant alias management (#114)
# ---------------------------------------------------------------------------

class TestMerchantAliases:
    def test_empty_list(self, client, auth_header):
        r = client.get("/merchant-aliases", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data == []

    def test_create_alias(self, client, auth_header):
        r = client.post(
            "/merchant-aliases",
            json={"raw_name": "NETFLIX.COM *123", "canonical_name": "Netflix"},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["raw_name"] == "NETFLIX.COM *123"
        assert data["canonical_name"] == "Netflix"
        assert "id" in data

    def test_list_alias_after_create(self, client, auth_header):
        client.post(
            "/merchant-aliases",
            json={"raw_name": "AMZN MKTP US", "canonical_name": "Amazon"},
            headers=auth_header,
        )
        r = client.get("/merchant-aliases", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) >= 1
        names = [a["canonical_name"] for a in data]
        assert "Amazon" in names

    def test_upsert_alias(self, client, auth_header):
        # Create then update
        client.post(
            "/merchant-aliases",
            json={"raw_name": "SP*SPOTIFY", "canonical_name": "Spotify Music"},
            headers=auth_header,
        )
        r = client.post(
            "/merchant-aliases",
            json={"raw_name": "SP*SPOTIFY", "canonical_name": "Spotify"},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["canonical_name"] == "Spotify"

    def test_create_alias_missing_fields(self, client, auth_header):
        r = client.post(
            "/merchant-aliases",
            json={"raw_name": "foo"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_delete_alias(self, client, auth_header):
        r = client.post(
            "/merchant-aliases",
            json={"raw_name": "TO_DELETE", "canonical_name": "Delete Me"},
            headers=auth_header,
        )
        alias_id = r.get_json()["id"]

        r = client.delete(f"/merchant-aliases/{alias_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["status"] == "deleted"

        # Verify it's gone
        r = client.get("/merchant-aliases", headers=auth_header)
        ids = [a["id"] for a in r.get_json()]
        assert alias_id not in ids

    def test_delete_nonexistent_alias(self, client, auth_header):
        r = client.delete("/merchant-aliases/999999", headers=auth_header)
        assert r.status_code == 404

    def test_resolve_known_merchant(self, client, auth_header):
        client.post(
            "/merchant-aliases",
            json={"raw_name": "HULU LLC", "canonical_name": "Hulu"},
            headers=auth_header,
        )
        r = client.get(
            "/merchant-aliases/resolve?raw_name=HULU LLC", headers=auth_header
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["canonical_name"] == "Hulu"

    def test_resolve_unknown_merchant_returns_raw(self, client, auth_header):
        r = client.get(
            "/merchant-aliases/resolve?raw_name=UNKNOWN PAYEE XYZ",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["canonical_name"] == "UNKNOWN PAYEE XYZ"
        assert data["raw_name"] == "UNKNOWN PAYEE XYZ"

    def test_resolve_requires_raw_name(self, client, auth_header):
        r = client.get("/merchant-aliases/resolve", headers=auth_header)
        assert r.status_code == 400

    def test_requires_auth(self, client):
        r = client.get("/merchant-aliases")
        assert r.status_code == 401
