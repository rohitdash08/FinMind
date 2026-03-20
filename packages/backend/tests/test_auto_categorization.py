"""Tests for Intelligent Transaction Categorization Engine."""
import pytest
from unittest.mock import patch, MagicMock

from app.services.auto_categorization import (
    _match_rules,
    get_category_suggestion,
    auto_categorize_batch,
    CATEGORIZATION_RULES,
    _COMPILED_RULES,
)


# ──────────────────────────────────────────────
# Rule-based matching
# ──────────────────────────────────────────────

def test_match_starbucks():
    cat, conf, source = _match_rules("STARBUCKS #12345")
    assert cat == "Food & Dining"
    assert conf >= 0.90
    assert source == "rule"


def test_match_netflix():
    cat, conf, source = _match_rules("Netflix Monthly Subscription")
    assert cat == "Entertainment"
    assert conf >= 0.90
    assert source == "rule"


def test_match_uber():
    cat, conf, source = _match_rules("UBER * TRIP 20MAR")
    assert cat == "Transportation"
    assert conf >= 0.85
    assert source == "rule"


def test_match_whole_foods():
    cat, conf, source = _match_rules("WHOLE FOODS MKT #123")
    assert cat == "Groceries"
    assert conf >= 0.85
    assert source == "rule"


def test_match_amazon():
    cat, conf, source = _match_rules("AMAZON MARKETPLACE")
    assert cat == "Shopping"
    assert conf >= 0.85
    assert source == "rule"


def test_match_gym():
    cat, conf, source = _match_rules("Planet Fitness membership fee")
    assert cat == "Health"
    assert conf >= 0.85
    assert source == "rule"


def test_match_unknown_falls_back():
    cat, conf, source = _match_rules("UNKNOWN MERCHANT XYZ")
    assert cat == "Uncategorized"
    assert conf < 0.50
    assert source == "fallback"


def test_match_case_insensitive():
    cat1, _, _ = _match_rules("netflix")
    cat2, _, _ = _match_rules("NETFLIX")
    assert cat1 == cat2


def test_match_insurance():
    cat, conf, source = _match_rules("GEICO Auto Insurance Premium")
    assert cat == "Insurance"
    assert conf >= 0.85


def test_match_pharmacy():
    cat, conf, source = _match_rules("CVS Pharmacy #9876")
    assert cat == "Health"
    assert conf >= 0.85


# ──────────────────────────────────────────────
# get_category_suggestion (no DB modification)
# ──────────────────────────────────────────────

def test_get_suggestion_rule_hit():
    with patch("app.services.auto_categorization.Expense") as MockExp, \
         patch("app.services.auto_categorization.Category") as MockCat:
        MockExp.query.filter.return_value.order_by.return_value.first.return_value = None
        result = get_category_suggestion(1, "SPOTIFY PREMIUM")
        assert result["suggested_category"] == "Entertainment"
        assert result["confidence"] >= 0.90
        assert result["source"] == "rule"


def test_get_suggestion_fallback():
    with patch("app.services.auto_categorization.Expense") as MockExp, \
         patch("app.services.auto_categorization.Category") as MockCat:
        MockExp.query.filter.return_value.order_by.return_value.first.return_value = None
        result = get_category_suggestion(1, "SOME RANDOM THING 123")
        assert result["suggested_category"] == "Uncategorized"
        assert result["source"] == "fallback"


# ──────────────────────────────────────────────
# auto_categorize_batch
# ──────────────────────────────────────────────

def test_batch_categorize_applies_high_confidence():
    mock_expense = MagicMock()
    mock_expense.id = 1
    mock_expense.description = "Netflix Monthly"
    mock_expense.amount = 15.99
    mock_expense.category_id = None

    mock_category = MagicMock()
    mock_category.id = 5
    mock_category.name = "Entertainment"

    with patch("app.services.auto_categorization.Expense") as MockExp, \
         patch("app.services.auto_categorization.Category") as MockCat, \
         patch("app.services.auto_categorization.db") as MockDb:
        MockExp.query.filter.return_value.limit.return_value.all.return_value = [mock_expense]
        MockExp.query.filter.return_value.order_by.return_value.first.return_value = None
        MockCat.query.filter_by.return_value.first.return_value = mock_category

        result = auto_categorize_batch(1, 0.75)
        assert result["applied"] >= 1
        assert result["total_uncategorized"] == 1


def test_batch_skips_low_confidence():
    mock_expense = MagicMock()
    mock_expense.id = 2
    mock_expense.description = "RANDOM UNRECOGNIZED VENDOR"
    mock_expense.amount = 50.0
    mock_expense.category_id = None

    with patch("app.services.auto_categorization.Expense") as MockExp, \
         patch("app.services.auto_categorization.Category") as MockCat, \
         patch("app.services.auto_categorization.db") as MockDb:
        MockExp.query.filter.return_value.limit.return_value.all.return_value = [mock_expense]
        MockExp.query.filter.return_value.order_by.return_value.first.return_value = None

        result = auto_categorize_batch(1, 0.75)
        assert result["skipped"] >= 1


def test_rules_count():
    """Sanity check that we have a reasonable number of rules."""
    assert len(CATEGORIZATION_RULES) >= 25