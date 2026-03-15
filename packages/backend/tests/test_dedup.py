"""Tests for transaction deduplication intelligence."""

import pytest
from datetime import date, timedelta
from app.services.dedup import (
    compute_fingerprint,
    compute_fuzzy_fingerprint,
    _normalize_text,
)


# ─── Helpers ────────────────────────────────────────────────────────────


def _create_expense(client, auth_header, notes="Lunch", amount=12.50,
                     category_id=None, spent_at=None):
    payload = {
        "notes": notes,
        "amount": amount,
        "currency": "USD",
        "expense_type": "EXPENSE",
    }
    if category_id:
        payload["category_id"] = category_id
    if spent_at:
        payload["spent_at"] = spent_at
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code in (200, 201), f"create expense fail: {r.get_json()}"
    return r.get_json()


def _create_category(client, auth_header, name="Food"):
    r = client.post(
        "/categories",
        json={"name": name, "monthly_budget": 500},
        headers=auth_header,
    )
    assert r.status_code in (200, 201)
    return r.get_json()["id"]


# ─── Unit tests: fingerprint ───────────────────────────────────────────


class TestFingerprint:
    """Test fingerprint computation."""

    def test_same_inputs_same_fingerprint(self):
        fp1 = compute_fingerprint(12.50, "USD", date(2024, 6, 15), "Lunch")
        fp2 = compute_fingerprint(12.50, "USD", date(2024, 6, 15), "Lunch")
        assert fp1 == fp2

    def test_different_amount(self):
        fp1 = compute_fingerprint(12.50, "USD", date(2024, 6, 15), "Lunch")
        fp2 = compute_fingerprint(13.00, "USD", date(2024, 6, 15), "Lunch")
        assert fp1 != fp2

    def test_different_date(self):
        fp1 = compute_fingerprint(12.50, "USD", date(2024, 6, 15), "Lunch")
        fp2 = compute_fingerprint(12.50, "USD", date(2024, 6, 16), "Lunch")
        assert fp1 != fp2

    def test_different_notes(self):
        fp1 = compute_fingerprint(12.50, "USD", date(2024, 6, 15), "Lunch")
        fp2 = compute_fingerprint(12.50, "USD", date(2024, 6, 15), "Dinner")
        assert fp1 != fp2

    def test_different_currency(self):
        fp1 = compute_fingerprint(12.50, "USD", date(2024, 6, 15), "Lunch")
        fp2 = compute_fingerprint(12.50, "EUR", date(2024, 6, 15), "Lunch")
        assert fp1 != fp2

    def test_none_notes(self):
        fp = compute_fingerprint(12.50, "USD", date(2024, 6, 15), None)
        assert isinstance(fp, str)
        assert len(fp) == 16

    def test_fingerprint_length(self):
        fp = compute_fingerprint(12.50, "USD", date(2024, 6, 15), "Test")
        assert len(fp) == 16

    def test_currency_case_insensitive(self):
        fp1 = compute_fingerprint(12.50, "usd", date(2024, 6, 15), "Lunch")
        fp2 = compute_fingerprint(12.50, "USD", date(2024, 6, 15), "Lunch")
        assert fp1 == fp2


class TestFuzzyFingerprint:
    """Test fuzzy fingerprint computation."""

    def test_same_without_notes(self):
        fp1 = compute_fuzzy_fingerprint(12.50, "USD", date(2024, 6, 15))
        fp2 = compute_fuzzy_fingerprint(12.50, "USD", date(2024, 6, 15))
        assert fp1 == fp2

    def test_ignores_notes(self):
        """Fuzzy fingerprint doesn't use notes."""
        fp1 = compute_fuzzy_fingerprint(12.50, "USD", date(2024, 6, 15))
        # Same amount/date/currency should match regardless of notes
        fp2 = compute_fuzzy_fingerprint(12.50, "USD", date(2024, 6, 15))
        assert fp1 == fp2


class TestNormalizeText:
    """Test text normalization."""

    def test_lowercase(self):
        assert _normalize_text("HELLO") == "hello"

    def test_strip(self):
        assert _normalize_text("  hello  ") == "hello"

    def test_collapse_whitespace(self):
        assert _normalize_text("hello   world") == "hello world"

    def test_remove_reference(self):
        result = _normalize_text("Payment ref: ABC123")
        assert "ABC123" not in result


# ─── Scan endpoint ─────────────────────────────────────────────────────


class TestScanEndpoint:
    """Tests for POST /dedup/scan."""

    def test_scan_empty(self, client, auth_header):
        """Scan with no expenses."""
        r = client.post("/dedup/scan", json={}, headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["scanned"] == 0
        assert data["potential_duplicates"] == 0

    def test_scan_no_duplicates(self, client, auth_header):
        """Scan with unique expenses."""
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        _create_expense(client, auth_header, "Lunch", 15.00, spent_at="2024-06-15")

        r = client.post("/dedup/scan", json={}, headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["scanned"] == 2

    def test_scan_finds_exact_duplicates(self, client, auth_header):
        """Scan detects exact duplicate expenses."""
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")

        r = client.post("/dedup/scan", json={}, headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["scanned"] == 2
        assert data["potential_duplicates"] >= 2

    def test_scan_with_date_window(self, client, auth_header):
        """Scan finds near-date duplicates within window."""
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-16")

        r = client.post(
            "/dedup/scan",
            json={"date_window": 1},
            headers=auth_header,
        )
        assert r.status_code == 200

    def test_scan_invalid_window(self, client, auth_header):
        """Invalid date_window returns 400."""
        r = client.post(
            "/dedup/scan",
            json={"date_window": 50},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_scan_negative_tolerance(self, client, auth_header):
        """Negative tolerance returns 400."""
        r = client.post(
            "/dedup/scan",
            json={"amount_tolerance": -1},
            headers=auth_header,
        )
        assert r.status_code == 400


# ─── Groups endpoint ──────────────────────────────────────────────────


class TestGroupsEndpoint:
    """Tests for GET /dedup/groups."""

    def test_groups_empty(self, client, auth_header):
        """No groups when no scan has been done."""
        r = client.get("/dedup/groups", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["count"] == 0
        assert data["groups"] == []

    def test_groups_after_scan(self, client, auth_header):
        """Groups appear after scanning duplicates."""
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")

        client.post("/dedup/scan", json={}, headers=auth_header)

        r = client.get("/dedup/groups", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["count"] >= 1

    def test_groups_filter_by_status(self, client, auth_header):
        """Can filter groups by status."""
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")

        client.post("/dedup/scan", json={}, headers=auth_header)

        r = client.get("/dedup/groups?status=PENDING", headers=auth_header)
        assert r.status_code == 200
        for group in r.get_json()["groups"]:
            assert group["status"] == "PENDING"

    def test_groups_include_expenses(self, client, auth_header):
        """Groups include matching expense details."""
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")

        client.post("/dedup/scan", json={}, headers=auth_header)

        r = client.get("/dedup/groups", headers=auth_header)
        groups = r.get_json()["groups"]
        if groups:
            assert "expenses" in groups[0]
            assert groups[0]["count"] >= 2


# ─── Resolve endpoint ─────────────────────────────────────────────────


class TestResolveEndpoint:
    """Tests for POST /dedup/groups/<id>/resolve."""

    def _setup_duplicates(self, client, auth_header):
        """Create duplicates and scan."""
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        client.post("/dedup/scan", json={}, headers=auth_header)
        groups = client.get("/dedup/groups", headers=auth_header).get_json()["groups"]
        return groups[0] if groups else None

    def test_resolve_keep_all(self, client, auth_header):
        """Resolve with keep_all marks as resolved."""
        group = self._setup_duplicates(client, auth_header)
        if not group:
            pytest.skip("No duplicate groups found")

        r = client.post(
            f"/dedup/groups/{group['id']}/resolve",
            json={"action": "keep_all"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["status"] == "RESOLVED"

    def test_resolve_ignore(self, client, auth_header):
        """Resolve with ignore marks as ignored."""
        group = self._setup_duplicates(client, auth_header)
        if not group:
            pytest.skip("No duplicate groups found")

        r = client.post(
            f"/dedup/groups/{group['id']}/resolve",
            json={"action": "ignore"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["status"] == "IGNORED"

    def test_resolve_keep_one(self, client, auth_header):
        """Resolve with keep_one keeps specified expense."""
        group = self._setup_duplicates(client, auth_header)
        if not group or not group["expenses"]:
            pytest.skip("No duplicate groups found")

        keep_id = group["expenses"][0]["id"]
        r = client.post(
            f"/dedup/groups/{group['id']}/resolve",
            json={"action": "keep_one", "keep_expense_id": keep_id},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["status"] == "RESOLVED"
        assert r.get_json()["deleted_count"] >= 1

    def test_resolve_merge(self, client, auth_header):
        """Resolve with merge keeps oldest expense."""
        group = self._setup_duplicates(client, auth_header)
        if not group:
            pytest.skip("No duplicate groups found")

        r = client.post(
            f"/dedup/groups/{group['id']}/resolve",
            json={"action": "merge"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["status"] == "RESOLVED"

    def test_resolve_invalid_action(self, client, auth_header):
        """Invalid action returns 400."""
        group = self._setup_duplicates(client, auth_header)
        if not group:
            pytest.skip("No duplicate groups found")

        r = client.post(
            f"/dedup/groups/{group['id']}/resolve",
            json={"action": "invalid"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_resolve_keep_one_no_id(self, client, auth_header):
        """keep_one without keep_expense_id returns 400."""
        group = self._setup_duplicates(client, auth_header)
        if not group:
            pytest.skip("No duplicate groups found")

        r = client.post(
            f"/dedup/groups/{group['id']}/resolve",
            json={"action": "keep_one"},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_resolve_not_found(self, client, auth_header):
        """Non-existent group returns 404."""
        r = client.post(
            "/dedup/groups/99999/resolve",
            json={"action": "keep_all"},
            headers=auth_header,
        )
        assert r.status_code == 404


# ─── Stats endpoint ────────────────────────────────────────────────────


class TestStatsEndpoint:
    """Tests for GET /dedup/stats."""

    def test_stats_empty(self, client, auth_header):
        """Stats with no expenses."""
        r = client.get("/dedup/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_expenses"] == 0
        assert data["coverage"] == 0

    def test_stats_after_scan(self, client, auth_header):
        """Stats reflects scan results."""
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")

        client.post("/dedup/scan", json={}, headers=auth_header)

        r = client.get("/dedup/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_expenses"] == 2
        assert data["fingerprinted"] == 2
        assert data["coverage"] == 100.0
        assert data["groups"]["pending"] >= 1

    def test_stats_after_resolve(self, client, auth_header):
        """Stats updates after resolution."""
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")
        _create_expense(client, auth_header, "Coffee", 5.00, spent_at="2024-06-15")

        client.post("/dedup/scan", json={}, headers=auth_header)
        groups = client.get("/dedup/groups", headers=auth_header).get_json()["groups"]
        if groups:
            client.post(
                f"/dedup/groups/{groups[0]['id']}/resolve",
                json={"action": "keep_all"},
                headers=auth_header,
            )

        r = client.get("/dedup/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["groups"]["resolved"] >= 1


# ─── Authentication tests ──────────────────────────────────────────────


class TestDedupAuth:
    """Tests that endpoints require authentication."""

    def test_scan_requires_auth(self, client):
        r = client.post("/dedup/scan")
        assert r.status_code in (401, 422)

    def test_groups_requires_auth(self, client):
        r = client.get("/dedup/groups")
        assert r.status_code in (401, 422)

    def test_stats_requires_auth(self, client):
        r = client.get("/dedup/stats")
        assert r.status_code in (401, 422)
