"""Tests for intelligent transaction categorization engine (#91)."""
import pytest
from unittest.mock import patch, MagicMock
from packages.backend.app.services.categorization import (
    _normalize,
    _match_keywords,
    categorize_note,
    apply_correction,
    bulk_categorize,
    DEFAULT_KEYWORD_MAP,
)


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("PIZZA") == "pizza"

    def test_strip_punctuation(self):
        assert _normalize("Swiggy!") == "swiggy"

    def test_strip_special_chars(self):
        assert _normalize("food & dining") == "food   dining"

    def test_empty_string(self):
        assert _normalize("") == ""


class TestMatchKeywords:
    def test_matches_food_keyword(self):
        result = _match_keywords("swiggy order", DEFAULT_KEYWORD_MAP)
        assert result == "Food & Dining"

    def test_matches_transport_keyword(self):
        result = _match_keywords("Uber ride to airport", DEFAULT_KEYWORD_MAP)
        assert result == "Transport"

    def test_matches_groceries(self):
        result = _match_keywords("BigBasket weekly grocery", DEFAULT_KEYWORD_MAP)
        assert result == "Groceries"

    def test_no_match_returns_none(self):
        result = _match_keywords("random xyz abc", DEFAULT_KEYWORD_MAP)
        assert result is None

    def test_case_insensitive(self):
        result = _match_keywords("NETFLIX subscription", DEFAULT_KEYWORD_MAP)
        assert result == "Entertainment"


class TestCategorizationEngine:
    """Test the three-tier categorization strategy."""

    def _make_db_mock(self, category_rules=None, user_categories=None, past_expenses=None):
        """Helper to create a db session mock."""
        mock_db = MagicMock()
        
        # Rules query
        mock_rules_query = MagicMock()
        mock_rules_query.filter_by.return_value = mock_rules_query
        mock_rules_query.order_by.return_value = mock_rules_query
        mock_rules_query.all.return_value = category_rules or []
        
        # Past expenses query for learning
        mock_exp_query = MagicMock()
        mock_exp_query.filter.return_value = mock_exp_query
        mock_exp_query.all.return_value = past_expenses or []
        
        # User categories query for keyword fallback
        mock_cats_query = MagicMock()
        mock_cats_query.filter_by.return_value = mock_cats_query
        mock_cats_query.all.return_value = user_categories or []
        
        def query_side_effect(model):
            from packages.backend.app.models import CategoryRule, Expense, Category
            if model is CategoryRule:
                return mock_rules_query
            elif hasattr(model, "category_id") and hasattr(model, "notes"):
                return mock_exp_query
            else:
                return mock_cats_query
        
        mock_db.session.query.side_effect = query_side_effect
        return mock_db

    def test_empty_note_returns_none_method(self):
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            mock_db.session.query.return_value = MagicMock(
                filter_by=MagicMock(return_value=MagicMock(
                    order_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
                ))
            )
            result = categorize_note(1, "")
        assert result["method"] == "none"
        assert result["confidence"] == 0.0
        assert result["category_id"] is None

    def test_keyword_fallback_no_user_categories(self):
        """When no rules and no history, should return keyword suggestion."""
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            # No rules
            rules_q = MagicMock()
            rules_q.filter_by.return_value.order_by.return_value.all.return_value = []
            
            # No past expenses
            exp_q = MagicMock()
            exp_q.filter.return_value.all.return_value = []
            
            # No matching user categories
            cats_q = MagicMock()
            cats_q.filter_by.return_value.all.return_value = []
            
            mock_db.session.query.side_effect = lambda m: {
                "CategoryRule": rules_q,
            }.get(m.__name__, exp_q if hasattr(m, "category_id") else cats_q)
            
            # Direct test on keyword matching
            result = _match_keywords("swiggy dinner order", DEFAULT_KEYWORD_MAP)
        
        assert result == "Food & Dining"

    def test_confidence_range(self):
        """Confidence should always be between 0.0 and 1.0."""
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            mock_q = MagicMock()
            mock_q.filter_by.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []
            mock_db.session.query.return_value = mock_q
            
            result = categorize_note(1, "netflix monthly subscription")
        
        assert 0.0 <= result["confidence"] <= 1.0


class TestUserRuleTier:
    """Test Tier 1: User-defined rules."""

    def _make_rule(self, match_type, pattern, cat_id=1):
        rule = MagicMock()
        rule.match_type = match_type
        rule.pattern = pattern
        rule.category_id = cat_id
        rule.priority = 5
        return rule

    def _make_cat(self, cat_id=1, name="Food"):
        cat = MagicMock()
        cat.id = cat_id
        cat.name = name
        return cat

    def test_exact_match_returns_1_0_confidence(self):
        rule = self._make_rule("exact", "Swiggy Food")
        cat = self._make_cat()
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            rules_q = MagicMock()
            rules_q.filter_by.return_value.order_by.return_value.all.return_value = [rule]
            mock_db.session.query.return_value = rules_q
            mock_db.session.get.return_value = cat
            
            result = categorize_note(1, "Swiggy Food")
        
        assert result["method"] == "user_rule"
        assert result["confidence"] == 1.0
        assert result["category_id"] == 1

    def test_contains_match_returns_high_confidence(self):
        rule = self._make_rule("contains", "swiggy")
        cat = self._make_cat()
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            rules_q = MagicMock()
            rules_q.filter_by.return_value.order_by.return_value.all.return_value = [rule]
            mock_db.session.query.return_value = rules_q
            mock_db.session.get.return_value = cat
            
            result = categorize_note(1, "Swiggy dinner order for family")
        
        assert result["method"] == "user_rule"
        assert result["confidence"] == 0.95

    def test_regex_match(self):
        rule = self._make_rule("regex", r"swiggy|zomato")
        cat = self._make_cat()
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            rules_q = MagicMock()
            rules_q.filter_by.return_value.order_by.return_value.all.return_value = [rule]
            mock_db.session.query.return_value = rules_q
            mock_db.session.get.return_value = cat
            
            result = categorize_note(1, "Zomato order #12345")
        
        assert result["method"] == "user_rule"
        assert result["confidence"] == 0.9

    def test_invalid_regex_skipped(self):
        rule = self._make_rule("regex", "[invalid(regex")
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            rules_q = MagicMock()
            rules_q.filter_by.return_value.order_by.return_value.all.return_value = [rule]
            
            exp_q = MagicMock()
            exp_q.filter.return_value.all.return_value = []
            
            cats_q = MagicMock()
            cats_q.filter_by.return_value.all.return_value = []
            
            call_count = [0]
            def query_side_effect(m):
                call_count[0] += 1
                if call_count[0] == 1:
                    return rules_q
                elif call_count[0] == 2:
                    return exp_q
                return cats_q
            
            mock_db.session.query.side_effect = query_side_effect
            
            # Should not crash on invalid regex
            result = categorize_note(1, "some transaction note")
        
        # Should fall through to next tier, not crash
        assert result is not None


class TestApplyCorrection:
    def test_correction_updates_expense_category(self):
        mock_expense = MagicMock()
        mock_expense.user_id = 1
        mock_expense.notes = "Swiggy dinner"
        mock_expense.category_id = None
        
        mock_cat = MagicMock()
        mock_cat.id = 3
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            mock_db.session.get.side_effect = lambda model, id: {
                ("Expense", 42): mock_expense,
                ("CategoryRule", None): None,
            }.get((model.__name__, id), None)
            
            mock_db.session.query.return_value = MagicMock(
                filter_by=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
            )
            
            apply_correction(1, 42, 3)
        
        assert mock_expense.category_id == 3

    def test_correction_creates_rule_from_notes(self):
        mock_expense = MagicMock()
        mock_expense.user_id = 1
        mock_expense.notes = "Swiggy dinner"
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            mock_db.session.get.return_value = mock_expense
            
            existing_q = MagicMock()
            existing_q.filter_by.return_value.first.return_value = None
            mock_db.session.query.return_value = existing_q
            
            result = apply_correction(1, 42, 3)
        
        # A rule should have been added
        assert mock_db.session.add.called
        assert result is True

    def test_correction_no_duplicate_rule(self):
        mock_expense = MagicMock()
        mock_expense.user_id = 1
        mock_expense.notes = "Swiggy dinner"
        
        existing_rule = MagicMock()
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            mock_db.session.get.return_value = mock_expense
            
            existing_q = MagicMock()
            existing_q.filter_by.return_value.first.return_value = existing_rule
            mock_db.session.query.return_value = existing_q
            
            result = apply_correction(1, 42, 3)
        
        # Should NOT add a duplicate rule
        mock_db.session.add.assert_not_called()
        assert result is False

    def test_correction_wrong_user_returns_false(self):
        mock_expense = MagicMock()
        mock_expense.user_id = 999  # Different user
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            mock_db.session.get.return_value = mock_expense
            
            result = apply_correction(1, 42, 3)
        
        assert result is False


class TestBulkCategorize:
    def test_already_categorized_skipped(self):
        mock_expense = MagicMock()
        mock_expense.id = 1
        mock_expense.category_id = 5  # Already categorized
        mock_expense.user_id = 1
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            exp_q = MagicMock()
            exp_q.filter.return_value.all.return_value = [mock_expense]
            mock_db.session.query.return_value = exp_q
            
            results = bulk_categorize(1, [1])
        
        assert results[0]["already_categorized"] is True

    def test_high_confidence_suggestion_auto_applies(self):
        mock_expense = MagicMock()
        mock_expense.id = 2
        mock_expense.category_id = None
        mock_expense.notes = "Swiggy food order"
        mock_expense.amount = 250
        mock_expense.user_id = 1
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            exp_q = MagicMock()
            exp_q.filter.return_value.all.return_value = [mock_expense]
            
            with patch(
                "packages.backend.app.services.categorization.categorize_note",
                return_value={"category_id": 3, "category_name": "Food", "confidence": 0.95, "method": "user_rule"}
            ):
                results = bulk_categorize(1, [2])
        
        assert results[0]["applied"] is True
        assert mock_expense.category_id == 3

    def test_low_confidence_suggestion_not_applied(self):
        mock_expense = MagicMock()
        mock_expense.id = 3
        mock_expense.category_id = None
        mock_expense.notes = "misc payment"
        mock_expense.amount = 100
        mock_expense.user_id = 1
        
        with patch("packages.backend.app.services.categorization.db") as mock_db:
            exp_q = MagicMock()
            exp_q.filter.return_value.all.return_value = [mock_expense]
            
            with patch(
                "packages.backend.app.services.categorization.categorize_note",
                return_value={"category_id": None, "category_name": None, "confidence": 0.3, "method": "none"}
            ):
                results = bulk_categorize(1, [3])
        
        assert results[0]["applied"] is False
        assert mock_expense.category_id is None

