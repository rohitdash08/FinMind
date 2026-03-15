"""Tests for Rule-based Auto Tagging & Categorization (Issue #107)."""

import pytest


# ── Helpers ──────────────────────────────────────────────

def _create_category(client, hdr, name="Food"):
    r = client.post("/categories", json={"name": name}, headers=hdr)
    assert r.status_code in (200, 201)
    return r.get_json()["id"]


def _create_rule(client, hdr, name, pattern, **kwargs):
    data = {"name": name, "match_pattern": pattern, **kwargs}
    return client.post("/tagging/rules", json=data, headers=hdr)


def _add_expense(client, hdr, amount, currency="INR", notes="test"):
    return client.post(
        "/expenses",
        json={"amount": amount, "currency": currency, "notes": notes, "spent_at": "2026-03-10"},
        headers=hdr,
    )


# ── Rule CRUD ────────────────────────────────────────────

class TestRuleCRUD:
    def test_create_rule(self, client, auth_header):
        r = _create_rule(client, auth_header, "Uber rides", "uber")
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Uber rides"
        assert data["match_pattern"] == "uber"
        assert data["match_type"] == "contains"
        assert data["is_active"] is True

    def test_create_with_category(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Transport")
        r = _create_rule(
            client, auth_header, "Taxi", "taxi",
            assign_category_id=cat_id
        )
        assert r.status_code == 201
        assert r.get_json()["assign_category_id"] == cat_id

    def test_create_with_tags(self, client, auth_header):
        r = _create_rule(
            client, auth_header, "Groceries", "walmart",
            assign_tags="grocery,essential"
        )
        assert r.status_code == 201
        assert r.get_json()["assign_tags"] == "grocery,essential"

    def test_create_missing_fields(self, client, auth_header):
        r = client.post("/tagging/rules", json={"name": "test"}, headers=auth_header)
        assert r.status_code == 400

    def test_list_rules(self, client, auth_header):
        _create_rule(client, auth_header, "Rule 1", "pattern1")
        _create_rule(client, auth_header, "Rule 2", "pattern2")
        r = client.get("/tagging/rules", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_get_rule(self, client, auth_header):
        resp = _create_rule(client, auth_header, "Test", "test")
        rule_id = resp.get_json()["id"]
        r = client.get(f"/tagging/rules/{rule_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["name"] == "Test"

    def test_get_nonexistent(self, client, auth_header):
        r = client.get("/tagging/rules/9999", headers=auth_header)
        assert r.status_code == 404

    def test_update_rule(self, client, auth_header):
        resp = _create_rule(client, auth_header, "Old name", "old")
        rule_id = resp.get_json()["id"]
        r = client.put(
            f"/tagging/rules/{rule_id}",
            json={"name": "New name", "priority": 10},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["name"] == "New name"
        assert r.get_json()["priority"] == 10

    def test_delete_rule(self, client, auth_header):
        resp = _create_rule(client, auth_header, "To delete", "del")
        rule_id = resp.get_json()["id"]
        r = client.delete(f"/tagging/rules/{rule_id}", headers=auth_header)
        assert r.status_code == 200
        r = client.get(f"/tagging/rules/{rule_id}", headers=auth_header)
        assert r.status_code == 404

    def test_unauthenticated(self, client):
        r = client.get("/tagging/rules")
        assert r.status_code == 401


# ── Pattern Matching ─────────────────────────────────────

class TestPatternMatching:
    def test_contains_match(self, client, auth_header):
        _create_rule(client, auth_header, "Coffee", "coffee", assign_tags="caffeine")
        r = client.post(
            "/tagging/test",
            json={"notes": "Morning coffee at Starbucks", "amount": 5},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["count"] == 1

    def test_exact_match(self, client, auth_header):
        _create_rule(client, auth_header, "Exact", "uber", match_type="exact")
        # Should NOT match "uber ride" (not exact)
        r = client.post(
            "/tagging/test",
            json={"notes": "uber ride"},
            headers=auth_header,
        )
        assert r.get_json()["count"] == 0

        # Should match "uber" exactly
        r = client.post(
            "/tagging/test",
            json={"notes": "uber"},
            headers=auth_header,
        )
        assert r.get_json()["count"] == 1

    def test_starts_with_match(self, client, auth_header):
        _create_rule(client, auth_header, "Amazon", "amazon", match_type="starts_with")
        r = client.post(
            "/tagging/test",
            json={"notes": "Amazon Prime subscription"},
            headers=auth_header,
        )
        assert r.get_json()["count"] == 1

    def test_regex_match(self, client, auth_header):
        _create_rule(client, auth_header, "Numbers", r"\d{3,}", match_type="regex")
        r = client.post(
            "/tagging/test",
            json={"notes": "Invoice #12345"},
            headers=auth_header,
        )
        assert r.get_json()["count"] == 1

    def test_amount_range(self, client, auth_header):
        _create_rule(
            client, auth_header, "Big purchase", "purchase",
            min_amount=100, max_amount=1000
        )
        # Under minimum
        r = client.post(
            "/tagging/test",
            json={"notes": "Small purchase", "amount": 50},
            headers=auth_header,
        )
        assert r.get_json()["count"] == 0

        # In range
        r = client.post(
            "/tagging/test",
            json={"notes": "Medium purchase", "amount": 500},
            headers=auth_header,
        )
        assert r.get_json()["count"] == 1

    def test_currency_filter(self, client, auth_header):
        _create_rule(client, auth_header, "USD only", "expense", currency="USD")
        r = client.post(
            "/tagging/test",
            json={"notes": "USD expense", "currency": "USD"},
            headers=auth_header,
        )
        assert r.get_json()["count"] == 1

        r = client.post(
            "/tagging/test",
            json={"notes": "INR expense", "currency": "INR"},
            headers=auth_header,
        )
        assert r.get_json()["count"] == 0

    def test_no_match(self, client, auth_header):
        _create_rule(client, auth_header, "Pizza", "pizza")
        r = client.post(
            "/tagging/test",
            json={"notes": "Sushi dinner"},
            headers=auth_header,
        )
        assert r.get_json()["count"] == 0


# ── Bulk Apply ───────────────────────────────────────────

class TestBulkApply:
    def test_bulk_apply_categorizes(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Food")
        _create_rule(
            client, auth_header, "Food rule", "lunch",
            assign_category_id=cat_id
        )
        # Add uncategorized expense
        _add_expense(client, auth_header, 15, notes="Business lunch meeting")
        _add_expense(client, auth_header, 100, notes="Office supplies")

        r = client.post("/tagging/apply", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["expenses_checked"] >= 1
        assert data["expenses_updated"] >= 1

    def test_bulk_apply_empty(self, client, auth_header):
        r = client.post("/tagging/apply", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["expenses_updated"] == 0

    def test_priority_order(self, client, auth_header):
        cat1 = _create_category(client, auth_header, "Transport")
        cat2 = _create_category(client, auth_header, "Business")
        _create_rule(
            client, auth_header, "Low priority", "uber",
            assign_category_id=cat1, priority=1
        )
        _create_rule(
            client, auth_header, "High priority", "uber",
            assign_category_id=cat2, priority=10
        )
        # High priority rule should win
        r = client.post(
            "/tagging/test",
            json={"notes": "Uber to meeting"},
            headers=auth_header,
        )
        data = r.get_json()
        # Both match but high priority first
        assert data["count"] == 2
        assert data["matches"][0]["priority"] == 10
