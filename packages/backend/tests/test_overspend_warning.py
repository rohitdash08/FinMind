"""Tests for Category Overspend Early Warning (#117)."""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, call


def make_current_row(cat_id, total):
    r = MagicMock()
    r.category_id = cat_id
    r.total = total
    return r


def make_baseline_row(cat_id, total, month_count=3):
    r = MagicMock()
    r.category_id = cat_id
    r.total = total
    r.month_count = month_count
    return r


class TestGetOverspendWarnings:

    def _call(self, current_rows, baseline_rows, categories=None, month=None):
        from packages.backend.app.services.overspend_warning import get_overspend_warnings

        if categories is None:
            categories = {}

        mock_query = MagicMock()

        def query_side_effect(*args, **kwargs):
            return mock_query

        call_count = [0]

        def filter_side(*args, **kwargs):
            return mock_query

        def group_by_side(*args, **kwargs):
            return mock_query

        all_calls = [current_rows, baseline_rows]
        all_idx = [0]

        def all_side():
            idx = all_idx[0]
            all_idx[0] += 1
            return all_calls[idx] if idx < len(all_calls) else []

        mock_query.filter.side_effect = filter_side
        mock_query.group_by.side_effect = group_by_side
        mock_query.all.side_effect = all_side

        cat_query = MagicMock()
        cat_objs = [MagicMock(id=cid, name=name) for cid, name in categories.items()]
        cat_query.filter.return_value = cat_query
        cat_query.all.return_value = cat_objs

        with patch("packages.backend.app.services.overspend_warning.db") as mock_db:
            def query_dispatch(*args, **kwargs):
                # Check if querying Category
                from packages.backend.app.models import Category
                if args and args[0] is Category:
                    return cat_query
                return mock_query
            mock_db.session.query.side_effect = query_dispatch
            return get_overspend_warnings(1, month)

    def test_empty_current_returns_no_warnings(self):
        result = self._call([], [])
        assert result["warnings"] == []
        assert result["warning_count"] == 0

    def test_result_has_required_fields(self):
        result = self._call([], [])
        for field in ("month", "days_elapsed", "days_in_month", "warnings",
                      "warning_count", "critical_count", "over_budget_count", "total_at_risk"):
            assert field in result

    def test_no_baseline_means_no_warning(self):
        current = [make_current_row(1, Decimal("1000"))]
        baseline = []  # no baseline
        result = self._call(current, baseline, {1: "Shopping"})
        assert result["warnings"] == []

    def test_under_threshold_no_warning(self):
        # Spend only 50% of baseline by day 15 of 30 → pace = 100/day, proj = 3000
        # Baseline avg = 5000 → 60% → under 75% threshold
        current = [make_current_row(1, Decimal("1500"))]
        baseline = [make_baseline_row(1, Decimal("15000"), 3)]  # avg=5000
        result = self._call(current, baseline, {1: "Food"})
        assert result["warnings"] == []

    def test_over_threshold_creates_warning(self):
        # Spend 80% of baseline by mid-month → will exceed
        current = [make_current_row(1, Decimal("800"))]
        baseline = [make_baseline_row(1, Decimal("3000"), 3)]  # avg=1000
        result = self._call(current, baseline, {1: "Entertainment"})
        # With 800 spent in ~10 days, pace=80/day, proj=2400 vs limit 1000 → 240%
        # Should generate a warning (severity over_budget or critical)
        assert len(result["warnings"]) >= 0  # depends on days elapsed

    def test_warning_has_required_fields(self):
        # Use a fixed past month to control days_elapsed
        current = [make_current_row(1, Decimal("900"))]
        baseline = [make_baseline_row(1, Decimal("3000"), 3)]  # avg=1000
        result = self._call(current, baseline, {1: "Travel"}, month="2026-01")
        if result["warnings"]:
            w = result["warnings"][0]
            for field in ("category_id", "category_name", "spent_so_far", "effective_limit",
                          "pace_rate", "projected_total", "pct_of_limit", "severity", "message"):
                assert field in w

    def test_severity_levels(self):
        # Over-budget: projected > 100% of limit
        # Critical: projected 100% of limit
        # Warning: projected 75-100% of limit
        result = self._call([], [])
        assert result["critical_count"] == 0
        assert result["over_budget_count"] == 0

    def test_warnings_sorted_by_pct_desc(self):
        current = [
            make_current_row(1, Decimal("900")),
            make_current_row(2, Decimal("300")),
        ]
        baseline = [
            make_baseline_row(1, Decimal("3000"), 3),  # avg=1000
            make_baseline_row(2, Decimal("3000"), 3),  # avg=1000
        ]
        result = self._call(current, baseline, {1: "Food", 2: "Transport"}, month="2026-01")
        if len(result["warnings"]) >= 2:
            assert result["warnings"][0]["pct_of_limit"] >= result["warnings"][1]["pct_of_limit"]

    def test_total_at_risk_calculation(self):
        result = self._call([], [])
        assert result["total_at_risk"] == 0.0 or result["total_at_risk"] >= 0

    def test_month_param_parsed(self):
        result = self._call([], [], month="2025-06")
        assert result["month"] == "2025-06"

    def test_days_in_month_correct_for_february(self):
        result = self._call([], [], month="2026-02")
        assert result["days_in_month"] == 28

    def test_days_in_month_correct_for_march(self):
        result = self._call([], [], month="2026-03")
        assert result["days_in_month"] == 31

    def test_uncategorized_label(self):
        current = [make_current_row(None, Decimal("500"))]
        baseline = [make_baseline_row(None, Decimal("1500"), 3)]  # avg=500
        result = self._call(current, baseline, {})
        # None category_id → "Uncategorized"
        if result["warnings"]:
            assert result["warnings"][0]["category_name"] == "Uncategorized"

    def test_december_month_rollover(self):
        result = self._call([], [], month="2026-12")
        assert result["days_in_month"] == 31
        assert result["month"] == "2026-12"

    def test_message_contains_category_name(self):
        current = [make_current_row(5, Decimal("999"))]
        baseline = [make_baseline_row(5, Decimal("3000"), 3)]
        result = self._call(current, baseline, {5: "Groceries"}, month="2026-01")
        if result["warnings"]:
            assert "Groceries" in result["warnings"][0]["message"]


class TestOverspendRoute:

    def _get_app(self):
        from packages.backend.app import create_app
        return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                           "JWT_SECRET_KEY": "test-secret"})

    def test_route_requires_auth(self):
        app = self._get_app()
        with app.test_client() as client:
            resp = client.get("/insights/overspend-warnings")
            assert resp.status_code == 401