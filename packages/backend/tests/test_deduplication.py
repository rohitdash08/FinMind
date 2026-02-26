"""Tests for transaction deduplication intelligence."""

import pytest
from datetime import date


class TestDeduplication:
    """Tests for /duplicates endpoints."""

    def _seed_expenses(self, client, auth_header):
        """Create test expenses including duplicates."""
        expenses = [
            {"amount": 50.00, "notes": "Coffee at Starbucks", "spent_at": "2026-01-15"},
            {"amount": 50.00, "notes": "Coffee at Starbucks", "spent_at": "2026-01-15"},
            {"amount": 50.00, "notes": "coffee at starbucks", "spent_at": "2026-01-15"},
            {"amount": 75.00, "notes": "Grocery shopping", "spent_at": "2026-01-16"},
            {"amount": 75.00, "notes": "Grocery shopping", "spent_at": "2026-01-16"},
            {"amount": 100.00, "notes": "Unique expense", "spent_at": "2026-01-17"},
        ]
        ids = []
        for exp in expenses:
            r = client.post("/expenses/", json=exp, headers=auth_header)
            assert r.status_code in (200, 201)
            ids.append(r.get_json()["expense"]["id"])
        return ids

    def test_find_duplicates(self, client, auth_header):
        """Should detect duplicate groups."""
        self._seed_expenses(client, auth_header)
        r = client.get("/duplicates/", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_groups"] >= 2
        for group in data["duplicates"]:
            assert "anchor_id" in group
            assert "members" in group
            assert group["count"] >= 2
            for m in group["members"]:
                assert m["confidence"] >= 0.85

    def test_no_duplicates(self, client, auth_header):
        """Should return empty when no duplicates exist."""
        client.post(
            "/expenses/",
            json={"amount": 10.00, "notes": "A", "spent_at": "2026-01-01"},
            headers=auth_header,
        )
        client.post(
            "/expenses/",
            json={"amount": 20.00, "notes": "B", "spent_at": "2026-01-02"},
            headers=auth_header,
        )
        r = client.get("/duplicates/", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total_groups"] == 0

    def test_merge_duplicates(self, client, auth_header):
        """Should merge duplicates by removing extras."""
        ids = self._seed_expenses(client, auth_header)
        # ids[0], ids[1], ids[2] are duplicates (same amount+date+notes)
        r = client.post(
            "/duplicates/merge",
            json={"keep_id": ids[0], "remove_ids": [ids[1], ids[2]]},
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["merged"] == 2
        assert data["kept"] == ids[0]

    def test_merge_requires_fields(self, client, auth_header):
        """Should reject merge without required fields."""
        r = client.post("/duplicates/merge", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_requires_auth(self, client):
        """Should require authentication."""
        r = client.get("/duplicates/")
        assert r.status_code == 401
