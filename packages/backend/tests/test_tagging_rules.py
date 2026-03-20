"""
Tests for rule-based auto-tagging and categorization (issue #107).
"""
from __future__ import annotations
import pytest
from decimal import Decimal


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _register_and_login(client):
    client.post("/auth/register", json={"email": "tagger@test.com", "password": "pass1234"})
    r = client.post("/auth/login", json={"email": "tagger@test.com", "password": "pass1234"})
    token = r.get_json().get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


def _make_category(client, auth, name="Food"):
    r = client.post("/categories", json={"name": name}, headers=auth)
    return r.get_json().get("id")


def _make_expense(client, auth, notes="grocery shopping", amount=500.0, category_id=None):
    payload = {"amount": amount, "description": "test", "date": "2025-01-15"}
    if notes:
        payload["notes"] = notes
    if category_id:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth)
    return r.get_json()


def _create_rule(client, auth, **kwargs):
    defaults = {
        "name": "test rule",
        "match_field": "notes",
        "match_operator": "contains",
        "match_value": "grocery",
        "action_set_notes_tag": "food-shopping",
    }
    defaults.update(kwargs)
    r = client.post("/tagging-rules", json=defaults, headers=auth)
    return r


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestTaggingRulesAuth:
    def test_list_requires_auth(self, client):
        r = client.get("/tagging-rules")
        assert r.status_code == 401

    def test_create_requires_auth(self, client):
        r = client.post("/tagging-rules", json={})
        assert r.status_code == 401

    def test_apply_requires_auth(self, client):
        r = client.post("/tagging-rules/apply")
        assert r.status_code == 401

    def test_preview_requires_auth(self, client):
        r = client.post("/tagging-rules/preview", json={})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

class TestTaggingRulesCRUD:
    def test_create_rule_notes_contains(self, client):
        auth = _register_and_login(client)
        r = _create_rule(client, auth)
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "test rule"
        assert data["match_field"] == "notes"
        assert data["match_operator"] == "contains"
        assert data["match_value"] == "grocery"
        assert data["action_set_notes_tag"] == "food-shopping"
        assert data["active"] is True

    def test_create_rule_amount_gt(self, client):
        auth = _register_and_login(client)
        cat_id = _make_category(client, auth)
        r = _create_rule(client, auth,
            name="large expense",
            match_field="amount", match_operator="gt", match_value="1000",
            action_set_category_id=cat_id,
            action_set_notes_tag=None)
        assert r.status_code == 201
        data = r.get_json()
        assert data["action_set_category_id"] == cat_id

    def test_create_rule_validation_missing_name(self, client):
        auth = _register_and_login(client)
        r = client.post("/tagging-rules", json={
            "match_field": "notes", "match_operator": "contains",
            "match_value": "test", "action_set_notes_tag": "tag"
        }, headers=auth)
        assert r.status_code == 400

    def test_create_rule_validation_invalid_field(self, client):
        auth = _register_and_login(client)
        r = _create_rule(client, auth, match_field="invalid_field")
        assert r.status_code == 400

    def test_create_rule_validation_invalid_operator(self, client):
        auth = _register_and_login(client)
        r = _create_rule(client, auth, match_operator="regex")
        assert r.status_code == 400

    def test_create_rule_validation_incompatible_operator(self, client):
        auth = _register_and_login(client)
        r = _create_rule(client, auth, match_field="notes", match_operator="gt")
        assert r.status_code == 400

    def test_create_rule_validation_no_action(self, client):
        auth = _register_and_login(client)
        r = client.post("/tagging-rules", json={
            "name": "no action", "match_field": "notes",
            "match_operator": "contains", "match_value": "test"
        }, headers=auth)
        assert r.status_code == 400

    def test_list_rules_empty(self, client):
        auth = _register_and_login(client)
        r = client.get("/tagging-rules", headers=auth)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_list_rules_returns_created(self, client):
        auth = _register_and_login(client)
        _create_rule(client, auth, name="rule1")
        _create_rule(client, auth, name="rule2",
                     match_value="transport", action_set_notes_tag="travel")
        r = client.get("/tagging-rules", headers=auth)
        assert r.status_code == 200
        names = {rule["name"] for rule in r.get_json()}
        assert "rule1" in names
        assert "rule2" in names

    def test_get_single_rule(self, client):
        auth = _register_and_login(client)
        created = _create_rule(client, auth).get_json()
        r = client.get(f"/tagging-rules/{created[id]}", headers=auth)
        assert r.status_code == 200
        assert r.get_json()["id"] == created["id"]

    def test_get_nonexistent_rule(self, client):
        auth = _register_and_login(client)
        r = client.get("/tagging-rules/99999", headers=auth)
        assert r.status_code == 404

    def test_update_rule(self, client):
        auth = _register_and_login(client)
        created = _create_rule(client, auth).get_json()
        r = client.put(f"/tagging-rules/{created[id]}", json={
            "name": "updated rule",
            "match_field": "notes",
            "match_operator": "contains",
            "match_value": "restaurant",
            "action_set_notes_tag": "dining",
        }, headers=auth)
        assert r.status_code == 200
        data = r.get_json()
        assert data["name"] == "updated rule"
        assert data["match_value"] == "restaurant"

    def test_delete_rule(self, client):
        auth = _register_and_login(client)
        created = _create_rule(client, auth).get_json()
        r = client.delete(f"/tagging-rules/{created[id]}", headers=auth)
        assert r.status_code == 204
        r2 = client.get(f"/tagging-rules/{created[id]}", headers=auth)
        assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Apply rules tests
# ---------------------------------------------------------------------------

class TestApplyRules:
    def test_apply_notes_tag(self, client):
        auth = _register_and_login(client)
        exp = _make_expense(client, auth, notes="grocery shopping at market")
        _create_rule(client, auth, match_value="grocery", action_set_notes_tag="food")
        r = client.post("/tagging-rules/apply", headers=auth)
        assert r.status_code == 200
        data = r.get_json()
        assert data["expenses_updated"] >= 1

    def test_apply_sets_category(self, client):
        auth = _register_and_login(client)
        cat_id = _make_category(client, auth, "Groceries")
        _make_expense(client, auth, notes="weekly grocery run")
        _create_rule(client, auth, match_value="grocery",
                     action_set_category_id=cat_id, action_set_notes_tag=None)
        r = client.post("/tagging-rules/apply", headers=auth)
        assert r.status_code == 200
        assert r.get_json()["expenses_updated"] >= 1

    def test_apply_returns_rule_count(self, client):
        auth = _register_and_login(client)
        _create_rule(client, auth, name="r1")
        _create_rule(client, auth, name="r2", match_value="uber",
                     action_set_notes_tag="transport")
        r = client.post("/tagging-rules/apply", headers=auth)
        assert r.status_code == 200
        assert r.get_json()["rules_applied"] == 2

    def test_apply_no_expenses(self, client):
        auth = _register_and_login(client)
        _create_rule(client, auth)
        r = client.post("/tagging-rules/apply", headers=auth)
        assert r.status_code == 200
        assert r.get_json()["expenses_updated"] == 0


# ---------------------------------------------------------------------------
# Preview rule tests
# ---------------------------------------------------------------------------

class TestPreviewRule:
    def test_preview_shows_matches(self, client):
        auth = _register_and_login(client)
        _make_expense(client, auth, notes="uber ride to work")
        _make_expense(client, auth, notes="grocery shopping")
        r = client.post("/tagging-rules/preview", json={
            "name": "uber rule",
            "match_field": "notes",
            "match_operator": "contains",
            "match_value": "uber",
            "action_set_notes_tag": "transport",
        }, headers=auth)
        assert r.status_code == 200
        data = r.get_json()
        assert data["matched_count"] == 1
        assert len(data["matched_expenses"]) == 1

    def test_preview_no_match(self, client):
        auth = _register_and_login(client)
        _make_expense(client, auth, notes="grocery shopping")
        r = client.post("/tagging-rules/preview", json={
            "name": "rent rule",
            "match_field": "notes",
            "match_operator": "contains",
            "match_value": "monthly rent",
            "action_set_notes_tag": "housing",
        }, headers=auth)
        assert r.status_code == 200
        assert r.get_json()["matched_count"] == 0

    def test_preview_validation_error(self, client):
        auth = _register_and_login(client)
        r = client.post("/tagging-rules/preview", json={
            "name": "bad rule",
            "match_field": "invalid",
            "match_operator": "contains",
            "match_value": "test",
            "action_set_notes_tag": "tag",
        }, headers=auth)
        assert r.status_code == 400
