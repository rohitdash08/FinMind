"""Tests for database indexing optimization (Issue #128).

Covers:
  - Model index definitions
  - Index verification service
  - Query pattern analysis
  - Coverage reporting
  - Performance benchmarking
  - Table statistics
  - API endpoints
"""

import pytest
from datetime import date
from decimal import Decimal

from app.models import (
    Expense, Category, Bill, Reminder, RecurringExpense,
    AdImpression, UserSubscription,
)
from app.services.indexing import (
    get_table_indexes,
    get_all_indexes,
    analyze_index_coverage,
    benchmark_expense_queries,
    get_table_statistics,
    COMMON_QUERY_PATTERNS,
    _is_prefix,
)
from app.extensions import db


# ─── Model index definition tests ──────────────────────────────────────


class TestModelIndexes:
    def test_expense_has_indexes(self, app_fixture):
        with app_fixture.app_context():
            indexes = get_table_indexes("expenses")
            index_names = [idx["name"] for idx in indexes]
            assert "idx_expenses_user_date" in index_names
            assert "idx_expenses_user_category_date" in index_names
            assert "idx_expenses_user_type" in index_names

    def test_category_has_index(self, app_fixture):
        with app_fixture.app_context():
            indexes = get_table_indexes("categories")
            index_names = [idx["name"] for idx in indexes]
            assert "idx_categories_user" in index_names

    def test_recurring_has_indexes(self, app_fixture):
        with app_fixture.app_context():
            indexes = get_table_indexes("recurring_expenses")
            index_names = [idx["name"] for idx in indexes]
            assert "idx_recurring_user_active" in index_names
            assert "idx_recurring_cadence" in index_names

    def test_bills_has_index(self, app_fixture):
        with app_fixture.app_context():
            indexes = get_table_indexes("bills")
            index_names = [idx["name"] for idx in indexes]
            assert "idx_bills_user_due" in index_names

    def test_reminders_has_indexes(self, app_fixture):
        with app_fixture.app_context():
            indexes = get_table_indexes("reminders")
            index_names = [idx["name"] for idx in indexes]
            assert "idx_reminders_user" in index_names
            assert "idx_reminders_pending" in index_names

    def test_ad_impressions_has_index(self, app_fixture):
        with app_fixture.app_context():
            indexes = get_table_indexes("ad_impressions")
            index_names = [idx["name"] for idx in indexes]
            assert "idx_ad_impressions_placement_date" in index_names


# ─── Index verification tests ──────────────────────────────────────────


class TestIndexVerification:
    def test_get_table_indexes_returns_list(self, app_fixture):
        with app_fixture.app_context():
            indexes = get_table_indexes("expenses")
            assert isinstance(indexes, list)
            for idx in indexes:
                assert "name" in idx
                assert "columns" in idx
                assert "unique" in idx

    def test_get_all_indexes_has_all_tables(self, app_fixture):
        with app_fixture.app_context():
            all_idx = get_all_indexes()
            expected_tables = [
                "users", "categories", "expenses", "recurring_expenses",
                "bills", "reminders",
            ]
            for table in expected_tables:
                assert table in all_idx

    def test_nonexistent_table_returns_empty(self, app_fixture):
        with app_fixture.app_context():
            indexes = get_table_indexes("nonexistent_table")
            assert indexes == []


# ─── Prefix utility tests ──────────────────────────────────────────────


class TestIsPrefix:
    def test_exact_match(self):
        assert _is_prefix(["a", "b"], ["a", "b"]) is True

    def test_prefix_match(self):
        assert _is_prefix(["a"], ["a", "b", "c"]) is True

    def test_no_match(self):
        assert _is_prefix(["a", "b"], ["b", "a"]) is False

    def test_too_long(self):
        assert _is_prefix(["a", "b", "c"], ["a", "b"]) is False

    def test_empty_required(self):
        assert _is_prefix([], ["a", "b"]) is True


# ─── Coverage analysis tests ───────────────────────────────────────────


class TestCoverageAnalysis:
    def test_analyze_returns_report(self, app_fixture):
        with app_fixture.app_context():
            report = analyze_index_coverage()
            assert "total_patterns" in report
            assert "covered" in report
            assert "missing" in report
            assert "coverage_percentage" in report
            assert "covered_patterns" in report
            assert "missing_patterns" in report

    def test_total_equals_covered_plus_missing(self, app_fixture):
        with app_fixture.app_context():
            report = analyze_index_coverage()
            assert report["total_patterns"] == report["covered"] + report["missing"]

    def test_coverage_percentage_valid(self, app_fixture):
        with app_fixture.app_context():
            report = analyze_index_coverage()
            assert 0 <= report["coverage_percentage"] <= 100

    def test_common_patterns_defined(self):
        assert len(COMMON_QUERY_PATTERNS) >= 5
        for pattern in COMMON_QUERY_PATTERNS:
            assert "name" in pattern
            assert "table" in pattern
            assert "columns" in pattern


# ─── Benchmark tests ───────────────────────────────────────────────────


class TestBenchmark:
    def test_benchmark_runs(self, app_fixture):
        with app_fixture.app_context():
            results = benchmark_expense_queries(1)
            assert isinstance(results, list)
            assert len(results) >= 3
            for r in results:
                assert "query" in r
                assert "execution_time_ms" in r
                assert "status" in r

    def test_benchmark_with_data(self, app_fixture):
        with app_fixture.app_context():
            for i in range(5):
                exp = Expense(
                    user_id=1, amount=Decimal("100"),
                    currency="INR", expense_type="EXPENSE",
                    notes=f"test item {i}", spent_at=date.today(),
                )
                db.session.add(exp)
            db.session.commit()
            results = benchmark_expense_queries(1)
            assert all(r["status"] == "ok" for r in results)


# ─── Table statistics tests ────────────────────────────────────────────


class TestTableStatistics:
    def test_returns_all_tables(self, app_fixture):
        with app_fixture.app_context():
            stats = get_table_statistics()
            assert isinstance(stats, list)
            table_names = [s["table"] for s in stats]
            assert "expenses" in table_names
            assert "users" in table_names

    def test_row_counts_are_integers(self, app_fixture):
        with app_fixture.app_context():
            stats = get_table_statistics()
            for s in stats:
                assert isinstance(s["row_count"], int)


# ─── API tests ──────────────────────────────────────────────────────────


class TestIndexingAPI:
    def test_list_indexes_endpoint(self, client, auth_header):
        resp = client.get("/admin/db/indexes", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_indexes" in data
        assert "tables" in data

    def test_coverage_endpoint(self, client, auth_header):
        resp = client.get("/admin/db/coverage", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "coverage_percentage" in data

    def test_statistics_endpoint(self, client, auth_header):
        resp = client.get("/admin/db/statistics", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_benchmark_endpoint(self, client, auth_header):
        resp = client.post("/admin/db/benchmark", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "benchmarks" in data

    def test_unauthorized(self, client):
        resp = client.get("/admin/db/indexes")
        assert resp.status_code == 401
