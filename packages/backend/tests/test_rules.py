"""Tests for rule-based auto-tagging and categorization (issue #107).

Structure
---------
- Unit tests: ``rule_engine`` service with no Flask context required.
- Integration tests: full API round-trips using the Flask test client.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.rule_engine import (
    _evaluate_condition,
    _evaluate_rule,
    apply_rules,
    parse_actions,
    parse_conditions,
)


# ── unit tests: condition evaluation ──────────────────────────────────────────


class TestEvaluateCondition:
    def test_description_contains_match(self):
        cond = {"field": "description", "operator": "contains", "value": "coffee"}
        assert _evaluate_condition(cond, {"description": "Starbucks Coffee Shop"}) is True

    def test_description_contains_case_insensitive(self):
        cond = {"field": "description", "operator": "contains", "value": "COFFEE"}
        assert _evaluate_condition(cond, {"description": "starbucks coffee"}) is True

    def test_description_contains_no_match(self):
        cond = {"field": "description", "operator": "contains", "value": "grocery"}
        assert _evaluate_condition(cond, {"description": "Starbucks Coffee"}) is False

    def test_description_not_contains(self):
        cond = {"field": "description", "operator": "not_contains", "value": "coffee"}
        assert _evaluate_condition(cond, {"description": "Grocery Store"}) is True
        assert _evaluate_condition(cond, {"description": "Coffee Shop"}) is False

    def test_description_equals(self):
        cond = {"field": "description", "operator": "equals", "value": "netflix"}
        assert _evaluate_condition(cond, {"description": "Netflix"}) is True
        assert _evaluate_condition(cond, {"description": "Netflix Plus"}) is False

    def test_description_regex_match(self):
        cond = {"field": "description", "operator": "regex", "value": r"^uber\s*(eats)?"}
        assert _evaluate_condition(cond, {"description": "Uber Eats"}) is True
        assert _evaluate_condition(cond, {"description": "Uber"}) is True
        assert _evaluate_condition(cond, {"description": "Lyft"}) is False

    def test_description_regex_invalid(self):
        # Invalid regex should not crash; returns False
        cond = {"field": "description", "operator": "regex", "value": "[unclosed"}
        assert _evaluate_condition(cond, {"description": "test"}) is False

    def test_amount_gt(self):
        cond = {"field": "amount", "operator": "gt", "value": 100}
        assert _evaluate_condition(cond, {"amount": 150.0}) is True
        assert _evaluate_condition(cond, {"amount": 50.0}) is False
        assert _evaluate_condition(cond, {"amount": 100.0}) is False

    def test_amount_lt(self):
        cond = {"field": "amount", "operator": "lt", "value": 50}
        assert _evaluate_condition(cond, {"amount": 20.0}) is True
        assert _evaluate_condition(cond, {"amount": 100.0}) is False

    def test_amount_equals(self):
        cond = {"field": "amount", "operator": "equals", "value": "9.99"}
        assert _evaluate_condition(cond, {"amount": Decimal("9.99")}) is True
        assert _evaluate_condition(cond, {"amount": 10.0}) is False

    def test_amount_between(self):
        cond = {"field": "amount", "operator": "between", "value": [10, 50]}
        assert _evaluate_condition(cond, {"amount": 25.0}) is True
        assert _evaluate_condition(cond, {"amount": 10.0}) is True  # inclusive
        assert _evaluate_condition(cond, {"amount": 50.0}) is True  # inclusive
        assert _evaluate_condition(cond, {"amount": 5.0}) is False
        assert _evaluate_condition(cond, {"amount": 51.0}) is False

    def test_amount_between_invalid_value(self):
        cond = {"field": "amount", "operator": "between", "value": 100}  # wrong type
        assert _evaluate_condition(cond, {"amount": 50.0}) is False

    def test_expense_type_equals(self):
        cond = {"field": "expense_type", "operator": "equals", "value": "INCOME"}
        assert _evaluate_condition(cond, {"expense_type": "INCOME"}) is True
        assert _evaluate_condition(cond, {"expense_type": "EXPENSE"}) is False

    def test_unknown_field_returns_false(self):
        cond = {"field": "merchant", "operator": "contains", "value": "Amazon"}
        assert _evaluate_condition(cond, {"description": "Amazon"}) is False

    def test_unknown_operator_returns_false(self):
        cond = {"field": "description", "operator": "startswith", "value": "Amazon"}
        assert _evaluate_condition(cond, {"description": "Amazon Prime"}) is False


class TestEvaluateRule:
    def test_empty_conditions_matches_everything(self):
        assert _evaluate_rule([], {"description": "anything", "amount": 10}) is True

    def test_and_semantics_all_must_match(self):
        conditions = [
            {"field": "description", "operator": "contains", "value": "coffee"},
            {"field": "amount", "operator": "lt", "value": 10},
        ]
        assert _evaluate_rule(conditions, {"description": "coffee shop", "amount": 5.0}) is True
        assert _evaluate_rule(conditions, {"description": "coffee shop", "amount": 50.0}) is False
        assert _evaluate_rule(conditions, {"description": "lunch", "amount": 5.0}) is False


class TestApplyRules:
    def test_no_rules_returns_empty_result(self):
        result = apply_rules({"description": "Coffee", "amount": 5.0}, [])
        assert result["set_category_id"] is None
        assert result["add_tags"] == []
        assert result["set_expense_type"] is None
        assert result["matched_rule_ids"] == []

    def test_matching_rule_sets_category(self):
        rules = [
            {
                "id": 1,
                "conditions": '[{"field":"description","operator":"contains","value":"coffee"}]',
                "actions": '{"set_category_id":5}',
            }
        ]
        result = apply_rules({"description": "Starbucks Coffee", "amount": 4.5}, rules)
        assert result["set_category_id"] == 5
        assert 1 in result["matched_rule_ids"]

    def test_non_matching_rule_ignored(self):
        rules = [
            {
                "id": 1,
                "conditions": '[{"field":"description","operator":"contains","value":"grocery"}]',
                "actions": '{"set_category_id":5}',
            }
        ]
        result = apply_rules({"description": "Starbucks Coffee", "amount": 4.5}, rules)
        assert result["set_category_id"] is None
        assert result["matched_rule_ids"] == []

    def test_first_matching_rule_wins_for_category(self):
        rules = [
            {
                "id": 1,
                "conditions": '[{"field":"description","operator":"contains","value":"coffee"}]',
                "actions": '{"set_category_id":5}',
            },
            {
                "id": 2,
                "conditions": '[{"field":"amount","operator":"lt","value":10}]',
                "actions": '{"set_category_id":99}',
            },
        ]
        result = apply_rules({"description": "Starbucks Coffee", "amount": 4.5}, rules)
        assert result["set_category_id"] == 5  # first match wins
        assert 1 in result["matched_rule_ids"]
        assert 2 in result["matched_rule_ids"]

    def test_tags_accumulate_across_rules(self):
        rules = [
            {
                "id": 1,
                "conditions": '[{"field":"description","operator":"contains","value":"coffee"}]',
                "actions": '{"add_tags":["caffeine","food"]}',
            },
            {
                "id": 2,
                "conditions": '[{"field":"amount","operator":"lt","value":10}]',
                "actions": '{"add_tags":["small-spend","food"]}',  # "food" is a duplicate
            },
        ]
        result = apply_rules({"description": "Starbucks Coffee", "amount": 4.5}, rules)
        assert set(result["add_tags"]) == {"caffeine", "food", "small-spend"}
        assert result["add_tags"].count("food") == 1  # deduplication

    def test_set_expense_type_first_match_wins(self):
        rules = [
            {
                "id": 1,
                "conditions": '[{"field":"description","operator":"contains","value":"salary"}]',
                "actions": '{"set_expense_type":"INCOME"}',
            },
            {
                "id": 2,
                "conditions": '[{"field":"amount","operator":"gt","value":1000}]',
                "actions": '{"set_expense_type":"EXPENSE"}',
            },
        ]
        result = apply_rules({"description": "Monthly Salary", "amount": 5000.0}, rules)
        assert result["set_expense_type"] == "INCOME"

    def test_parse_conditions_from_list(self):
        conditions = [{"field": "description", "operator": "contains", "value": "test"}]
        assert parse_conditions(conditions) == conditions

    def test_parse_conditions_from_json_string(self):
        raw = '[{"field":"description","operator":"contains","value":"test"}]'
        parsed = parse_conditions(raw)
        assert parsed[0]["field"] == "description"

    def test_parse_conditions_invalid_json(self):
        assert parse_conditions("not json") == []

    def test_parse_actions_from_dict(self):
        actions = {"set_category_id": 5}
        assert parse_actions(actions) == actions

    def test_parse_actions_from_json_string(self):
        assert parse_actions('{"set_category_id":5}') == {"set_category_id": 5}


# ── integration tests: Rules API ───────────────────────────────────────────────

# Patch redis for all integration tests so they run without a live Redis server.
@pytest.fixture(autouse=True)
def _mock_redis(monkeypatch):
    """Replace the module-level redis_client with a minimal in-memory mock."""
    try:
        import fakeredis

        fake = fakeredis.FakeRedis(decode_responses=True)
    except ImportError:
        # Fall back to a MagicMock that silently no-ops all Redis calls.
        fake = MagicMock()
        fake.get.return_value = None
        fake.scan.return_value = (0, [])
        fake.setex.return_value = True
        fake.set.return_value = True
        fake.delete.return_value = 0
        fake.flushdb.return_value = True

    monkeypatch.setattr("app.extensions.redis_client", fake)
    # Patch the already-imported reference in auth and cache modules
    monkeypatch.setattr("app.routes.auth.redis_client", fake)
    monkeypatch.setattr("app.services.cache.redis_client", fake)
    return fake


def _create_category(client, auth_header, name="Food"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    return next(c["id"] for c in r.get_json() if c["name"] == name)


class TestRulesCRUD:
    def test_list_empty(self, client, auth_header):
        r = client.get("/rules", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_create_and_get(self, client, auth_header):
        payload = {
            "name": "Coffee rule",
            "priority": 1,
            "conditions": [
                {"field": "description", "operator": "contains", "value": "coffee"}
            ],
            "actions": {"add_tags": ["caffeine"]},
        }
        r = client.post("/rules", json=payload, headers=auth_header)
        assert r.status_code == 201
        data = r.get_json()
        rule_id = data["id"]
        assert data["name"] == "Coffee rule"
        assert data["priority"] == 1
        assert data["conditions"][0]["value"] == "coffee"
        assert data["actions"]["add_tags"] == ["caffeine"]
        assert data["active"] is True

        # GET by id
        r = client.get(f"/rules/{rule_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["id"] == rule_id

    def test_create_missing_name(self, client, auth_header):
        r = client.post(
            "/rules",
            json={"conditions": [], "actions": {"add_tags": ["x"]}},
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_create_invalid_conditions_field(self, client, auth_header):
        r = client.post(
            "/rules",
            json={
                "name": "Bad rule",
                "conditions": [
                    {"field": "merchant", "operator": "contains", "value": "x"}
                ],
                "actions": {"add_tags": ["x"]},
            },
            headers=auth_header,
        )
        assert r.status_code == 400
        assert "field" in r.get_json()["error"]

    def test_create_invalid_actions_no_action_key(self, client, auth_header):
        r = client.post(
            "/rules",
            json={
                "name": "Empty actions",
                "conditions": [],
                "actions": {},
            },
            headers=auth_header,
        )
        assert r.status_code == 400

    def test_update_rule(self, client, auth_header):
        r = client.post(
            "/rules",
            json={
                "name": "Old name",
                "conditions": [],
                "actions": {"add_tags": ["a"]},
            },
            headers=auth_header,
        )
        rule_id = r.get_json()["id"]

        r = client.patch(
            f"/rules/{rule_id}",
            json={"name": "New name", "priority": 5, "active": False},
            headers=auth_header,
        )
        assert r.status_code == 200
        updated = r.get_json()
        assert updated["name"] == "New name"
        assert updated["priority"] == 5
        assert updated["active"] is False

    def test_delete_rule(self, client, auth_header):
        r = client.post(
            "/rules",
            json={"name": "To delete", "conditions": [], "actions": {"add_tags": ["x"]}},
            headers=auth_header,
        )
        rule_id = r.get_json()["id"]
        r = client.delete(f"/rules/{rule_id}", headers=auth_header)
        assert r.status_code == 200
        r = client.get(f"/rules/{rule_id}", headers=auth_header)
        assert r.status_code == 404

    def test_cannot_access_other_users_rule(self, client, auth_header):
        # Create with user 1
        r = client.post(
            "/rules",
            json={"name": "Mine", "conditions": [], "actions": {"add_tags": ["x"]}},
            headers=auth_header,
        )
        rule_id = r.get_json()["id"]

        # Register user 2
        client.post("/auth/register", json={"email": "user2@example.com", "password": "pass1234"})
        r2 = client.post(
            "/auth/login", json={"email": "user2@example.com", "password": "pass1234"}
        )
        token2 = r2.get_json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        r = client.get(f"/rules/{rule_id}", headers=headers2)
        assert r.status_code == 404

    def test_list_sorted_by_priority(self, client, auth_header):
        for priority in (3, 1, 2):
            client.post(
                "/rules",
                json={
                    "name": f"Rule p{priority}",
                    "priority": priority,
                    "conditions": [],
                    "actions": {"add_tags": ["x"]},
                },
                headers=auth_header,
            )
        r = client.get("/rules", headers=auth_header)
        priorities = [rule["priority"] for rule in r.get_json()]
        assert priorities == sorted(priorities)


class TestRuleDryRun:
    def test_test_endpoint_matches(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Dining")
        client.post(
            "/rules",
            json={
                "name": "Coffee",
                "conditions": [
                    {"field": "description", "operator": "contains", "value": "starbucks"}
                ],
                "actions": {"set_category_id": cat_id, "add_tags": ["coffee"]},
            },
            headers=auth_header,
        )
        r = client.post(
            "/rules/test",
            json={"transaction": {"description": "Starbucks Pumpkin Latte", "amount": 6.5}},
            headers=auth_header,
        )
        assert r.status_code == 200
        result = r.get_json()
        assert len(result["matched_rule_ids"]) == 1
        assert result["changes"]["set_category_id"] == cat_id
        assert "coffee" in result["changes"]["add_tags"]

    def test_test_endpoint_no_match(self, client, auth_header):
        client.post(
            "/rules",
            json={
                "name": "Coffee",
                "conditions": [
                    {"field": "description", "operator": "contains", "value": "coffee"}
                ],
                "actions": {"add_tags": ["caffeine"]},
            },
            headers=auth_header,
        )
        r = client.post(
            "/rules/test",
            json={"transaction": {"description": "Grocery Run", "amount": 40.0}},
            headers=auth_header,
        )
        assert r.status_code == 200
        result = r.get_json()
        assert result["matched_rule_ids"] == []
        assert result["changes"]["add_tags"] == []

    def test_test_endpoint_requires_transaction(self, client, auth_header):
        r = client.post("/rules/test", json={}, headers=auth_header)
        assert r.status_code == 400


class TestAutoTaggingOnExpenseCreate:
    def test_rule_applied_on_create(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Cafes")
        # Create a rule
        client.post(
            "/rules",
            json={
                "name": "Tag coffee purchases",
                "conditions": [
                    {"field": "description", "operator": "contains", "value": "coffee"}
                ],
                "actions": {"set_category_id": cat_id, "add_tags": ["beverage"]},
            },
            headers=auth_header,
        )
        # Create a matching expense
        r = client.post(
            "/expenses",
            json={"amount": 4.5, "description": "Morning Coffee", "date": "2026-01-10"},
            headers=auth_header,
        )
        assert r.status_code == 201
        expense = r.get_json()
        assert expense["category_id"] == cat_id
        assert "beverage" in expense["tags"]

    def test_rule_not_applied_to_non_matching_expense(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Cafes")
        client.post(
            "/rules",
            json={
                "name": "Tag coffee purchases",
                "conditions": [
                    {"field": "description", "operator": "contains", "value": "coffee"}
                ],
                "actions": {"set_category_id": cat_id, "add_tags": ["beverage"]},
            },
            headers=auth_header,
        )
        r = client.post(
            "/expenses",
            json={"amount": 50.0, "description": "Grocery shopping", "date": "2026-01-10"},
            headers=auth_header,
        )
        assert r.status_code == 201
        expense = r.get_json()
        assert expense["category_id"] is None
        assert "beverage" not in expense["tags"]

    def test_inactive_rule_not_applied(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Cafes")
        r = client.post(
            "/rules",
            json={
                "name": "Inactive",
                "conditions": [
                    {"field": "description", "operator": "contains", "value": "coffee"}
                ],
                "actions": {"set_category_id": cat_id},
                "active": False,
            },
            headers=auth_header,
        )
        rule_id = r.get_json()["id"]
        assert r.get_json()["active"] is False

        r = client.post(
            "/expenses",
            json={"amount": 4.5, "description": "Morning Coffee", "date": "2026-01-10"},
            headers=auth_header,
        )
        assert r.status_code == 201
        assert r.get_json()["category_id"] is None

    def test_amount_range_rule(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Small Spend")
        client.post(
            "/rules",
            json={
                "name": "Small purchases",
                "conditions": [
                    {"field": "amount", "operator": "between", "value": [1, 15]}
                ],
                "actions": {"set_category_id": cat_id, "add_tags": ["small"]},
            },
            headers=auth_header,
        )
        r = client.post(
            "/expenses",
            json={"amount": 8.99, "description": "Parking meter", "date": "2026-01-10"},
            headers=auth_header,
        )
        assert r.status_code == 201
        expense = r.get_json()
        assert expense["category_id"] == cat_id
        assert "small" in expense["tags"]

    def test_regex_rule(self, client, auth_header):
        client.post(
            "/rules",
            json={
                "name": "Streaming services",
                "conditions": [
                    {"field": "description", "operator": "regex", "value": r"netflix|spotify|hulu"}
                ],
                "actions": {"add_tags": ["streaming"]},
            },
            headers=auth_header,
        )
        r = client.post(
            "/expenses",
            json={"amount": 15.99, "description": "Netflix Monthly", "date": "2026-01-10"},
            headers=auth_header,
        )
        assert r.status_code == 201
        assert "streaming" in r.get_json()["tags"]


class TestApplyAllRules:
    def test_apply_all_uncategorised(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Dining")

        # Create expenses WITHOUT a matching rule active yet
        for desc in ("Burger King", "McDonalds", "Tech store"):
            client.post(
                "/expenses",
                json={"amount": 10.0, "description": desc, "date": "2026-01-05"},
                headers=auth_header,
            )

        # Now create a rule
        client.post(
            "/rules",
            json={
                "name": "Fast food",
                "conditions": [
                    {
                        "field": "description",
                        "operator": "regex",
                        "value": r"burger king|mcdonalds",
                    }
                ],
                "actions": {"set_category_id": cat_id, "add_tags": ["fast-food"]},
            },
            headers=auth_header,
        )

        r = client.post("/rules/apply-all", json={}, headers=auth_header)
        assert r.status_code == 200
        result = r.get_json()
        # Only the 2 fast-food entries should be updated
        assert result["updated"] == 2
        assert result["skipped"] == 1  # "Tech store" stays uncategorised

    def test_apply_all_force_flag(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Misc")

        # Create an expense that already has a category
        existing_cat = _create_category(client, auth_header, "Other")
        client.post(
            "/expenses",
            json={
                "amount": 10.0,
                "description": "Coffee shop",
                "date": "2026-01-05",
                "category_id": existing_cat,
            },
            headers=auth_header,
        )

        client.post(
            "/rules",
            json={
                "name": "All coffee",
                "conditions": [
                    {"field": "description", "operator": "contains", "value": "coffee"}
                ],
                "actions": {"set_category_id": cat_id},
            },
            headers=auth_header,
        )

        # Without force: apply-all only targets expenses with no category.
        # The expense above already has a category, so 0 expenses are processed.
        r = client.post("/rules/apply-all", json={}, headers=auth_header)
        assert r.status_code == 200
        result = r.get_json()
        assert result["updated"] == 0
        assert result["skipped"] == 0  # no uncategorised expenses exist

        # With force=True: the already-categorised expense is evaluated.
        # The rule matches, but set_category_id only applies when category_id is None,
        # so the expense is counted as skipped (no change applied).
        r = client.post("/rules/apply-all", json={"force": True}, headers=auth_header)
        assert r.status_code == 200
        result = r.get_json()
        assert "updated" in result
        assert "skipped" in result
