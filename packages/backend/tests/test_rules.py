"""
Tests for rule-based auto tagging engine.
"""

import pytest
from app.services.rule_engine import (
    create_rule,
    evaluate_condition,
    evaluate_rule,
    apply_rules_to_transaction,
)


class TestConditionEvaluation:
    def test_contains(self, app, db_session):
        with app.app_context():
            result = evaluate_condition(
                {"field": "merchant", "operator": "contains", "value": "starbucks"},
                {"merchant": "Starbucks Coffee #42"},
            )
            assert result is True

    def test_not_contains(self, app, db_session):
        with app.app_context():
            result = evaluate_condition(
                {"field": "merchant", "operator": "not_contains", "value": "coffee"},
                {"merchant": "Amazon.com"},
            )
            assert result is True

    def test_amount_greater(self, app, db_session):
        with app.app_context():
            result = evaluate_condition(
                {"field": "amount", "operator": "greater_than", "value": 50},
                {"amount": 75.50},
            )
            assert result is True

    def test_regex(self, app, db_session):
        with app.app_context():
            result = evaluate_condition(
                {"field": "merchant", "operator": "regex", "value": r"ama.*\.com"},
                {"merchant": "amazon.com"},
            )
            assert result is True

    def test_between(self, app, db_session):
        with app.app_context():
            result = evaluate_condition(
                {"field": "amount", "operator": "between", "min": 10, "max": 100, "value": 0},
                {"amount": 50},
            )
            assert result is True


class TestCompoundRules:
    def test_and_logic(self, app, db_session):
        with app.app_context():
            rule = create_rule(1, "Test AND", {
                "logic": "AND",
                "rules": [
                    {"field": "merchant", "operator": "contains", "value": "coffee"},
                    {"field": "amount", "operator": "greater_than", "value": 5},
                ],
            }, tag="expensive-coffee")

            result = evaluate_rule(rule, {"merchant": "Blue Bottle Coffee", "amount": 8})
            assert result is True

    def test_or_logic(self, app, db_session):
        with app.app_context():
            rule = create_rule(1, "Test OR", {
                "logic": "OR",
                "rules": [
                    {"field": "merchant", "operator": "contains", "value": "starbucks"},
                    {"field": "merchant", "operator": "contains", "value": "costa"},
                ],
            }, tag="coffee-shop")

            result = evaluate_rule(rule, {"merchant": "Costa Coffee"})
            assert result is True


class TestApplyRules:
    def test_apply_to_transaction(self, app, db_session):
        with app.app_context():
            create_rule(1, "Coffee Rule", {
                "field": "merchant", "operator": "contains", "value": "starbucks",
            }, tag="coffee", category="Food & Drink")

            mods = apply_rules_to_transaction(1, {"merchant": "Starbucks", "amount": 5})
            assert "coffee" in mods["tags"]
            assert mods["category"] == "Food & Drink"
