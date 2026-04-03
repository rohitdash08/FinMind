"""Tests for financial data integrity & reconciliation service (#96)."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, call
from packages.backend.app.services.integrity import (
    IntegrityAlert,
    check_duplicate_expenses,
    check_missing_categories,
    check_large_amounts,
    check_future_dates,
    check_orphaned_recurring,
    check_balance_consistency,
    run_integrity_check,
    get_reconciliation_summary,
    _get_monthly_net,
)


class TestIntegrityAlertConstants:
    def test_all_alert_types_defined(self):
        assert hasattr(IntegrityAlert, "DUPLICATE_EXPENSE")
        assert hasattr(IntegrityAlert, "BALANCE_MISMATCH")
        assert hasattr(IntegrityAlert, "MISSING_CATEGORY")
        assert hasattr(IntegrityAlert, "LARGE_AMOUNT")
        assert hasattr(IntegrityAlert, "FUTURE_DATE")
        assert hasattr(IntegrityAlert, "ORPHANED_RECURRING")


class TestDuplicateExpenseCheck:
    def _make_expense(self, id, amount, spent_at, category_id=1):
        e = MagicMock()
        e.id = id
        e.amount = amount
        e.spent_at = spent_at
        e.category_id = category_id
        return e

    def test_no_duplicates_returns_empty(self):
        today = date.today()
        expenses = [
            self._make_expense(1, 100, today),
            self._make_expense(2, 200, today),
            self._make_expense(3, 100, today - timedelta(days=1)),
        ]
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.order_by.return_value.all.return_value = expenses
            mock_db.session.query.return_value = q
            result = check_duplicate_expenses(1)
        assert result == []

    def test_exact_duplicates_detected(self):
        today = date.today()
        expenses = [
            self._make_expense(1, 500, today, category_id=2),
            self._make_expense(2, 500, today, category_id=2),  # Duplicate!
        ]
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.order_by.return_value.all.return_value = expenses
            mock_db.session.query.return_value = q
            result = check_duplicate_expenses(1)
        assert len(result) == 1
        assert result[0]["type"] == IntegrityAlert.DUPLICATE_EXPENSE
        assert set(result[0]["expense_ids"]) == {1, 2}

    def test_duplicate_alert_has_required_fields(self):
        today = date.today()
        expenses = [
            self._make_expense(3, 999, today),
            self._make_expense(4, 999, today),
        ]
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.order_by.return_value.all.return_value = expenses
            mock_db.session.query.return_value = q
            result = check_duplicate_expenses(1)
        assert "type" in result[0]
        assert "severity" in result[0]
        assert "expense_ids" in result[0]
        assert "message" in result[0]


class TestMissingCategoryCheck:
    def test_all_categorized_returns_empty(self):
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.all.return_value = []
            mock_db.session.query.return_value = q
            result = check_missing_categories(1)
        assert result == []

    def test_uncategorized_expenses_flagged(self):
        exp1 = MagicMock()
        exp1.id = 5
        exp2 = MagicMock()
        exp2.id = 6
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.all.return_value = [exp1, exp2]
            mock_db.session.query.return_value = q
            result = check_missing_categories(1)
        assert len(result) == 1
        assert result[0]["count"] == 2
        assert result[0]["type"] == IntegrityAlert.MISSING_CATEGORY
        assert 5 in result[0]["expense_ids"]
        assert 6 in result[0]["expense_ids"]


class TestFutureDateCheck:
    def test_no_future_dates_returns_empty(self):
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.all.return_value = []
            mock_db.session.query.return_value = q
            result = check_future_dates(1)
        assert result == []

    def test_future_dated_expenses_flagged(self):
        exp = MagicMock()
        exp.id = 10
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.all.return_value = [exp]
            mock_db.session.query.return_value = q
            result = check_future_dates(1)
        assert len(result) == 1
        assert result[0]["type"] == IntegrityAlert.FUTURE_DATE
        assert result[0]["severity"] == "warning"


class TestLargeAmountCheck:
    def test_no_large_amounts_returns_empty(self):
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            scalar_q = MagicMock()
            scalar_q.filter.return_value.scalar.return_value = 500  # avg
            
            large_q = MagicMock()
            large_q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            
            call_count = [0]
            def query_dispatch(model):
                call_count[0] += 1
                return scalar_q if call_count[0] == 1 else large_q
            
            mock_db.session.query.side_effect = query_dispatch
            result = check_large_amounts(1)
        assert result == []

    def test_no_avg_returns_empty(self):
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.scalar.return_value = None
            mock_db.session.query.return_value = q
            result = check_large_amounts(1)
        assert result == []


class TestOrphanedRecurringCheck:
    def test_no_orphaned_returns_empty(self):
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.all.return_value = []
            mock_db.session.query.return_value = q
            result = check_orphaned_recurring(1)
        assert result == []

    def test_orphaned_recurring_detected(self):
        rec = MagicMock()
        rec.id = 99
        with patch("packages.backend.app.services.integrity.db") as mock_db:
            q = MagicMock()
            q.filter.return_value.all.return_value = [rec]
            mock_db.session.query.return_value = q
            result = check_orphaned_recurring(1)
        assert len(result) == 1
        assert result[0]["type"] == IntegrityAlert.ORPHANED_RECURRING
        assert 99 in result[0]["recurring_ids"]


class TestRunIntegrityCheck:
    def test_returns_complete_structure(self):
        with patch("packages.backend.app.services.integrity.check_duplicate_expenses", return_value=[]):
            with patch("packages.backend.app.services.integrity.check_missing_categories", return_value=[]):
                with patch("packages.backend.app.services.integrity.check_large_amounts", return_value=[]):
                    with patch("packages.backend.app.services.integrity.check_future_dates", return_value=[]):
                        with patch("packages.backend.app.services.integrity.check_orphaned_recurring", return_value=[]):
                            with patch("packages.backend.app.services.integrity.check_balance_consistency", return_value=[]):
                                result = run_integrity_check(1)
        assert "total_issues" in result
        assert "alerts" in result
        assert "summary" in result
        assert "checked_at" in result

    def test_total_issues_counts_all_alerts(self):
        mock_alert = {"type": "test", "severity": "warning", "message": "test"}
        with patch("packages.backend.app.services.integrity.check_duplicate_expenses", return_value=[mock_alert]):
            with patch("packages.backend.app.services.integrity.check_missing_categories", return_value=[mock_alert]):
                with patch("packages.backend.app.services.integrity.check_large_amounts", return_value=[]):
                    with patch("packages.backend.app.services.integrity.check_future_dates", return_value=[]):
                        with patch("packages.backend.app.services.integrity.check_orphaned_recurring", return_value=[]):
                            with patch("packages.backend.app.services.integrity.check_balance_consistency", return_value=[]):
                                result = run_integrity_check(1)
        assert result["total_issues"] == 2

    def test_summary_by_severity(self):
        warning_alert = {"type": "t1", "severity": "warning", "message": "w"}
        info_alert = {"type": "t2", "severity": "info", "message": "i"}
        with patch("packages.backend.app.services.integrity.check_duplicate_expenses", return_value=[warning_alert]):
            with patch("packages.backend.app.services.integrity.check_missing_categories", return_value=[info_alert]):
                with patch("packages.backend.app.services.integrity.check_large_amounts", return_value=[]):
                    with patch("packages.backend.app.services.integrity.check_future_dates", return_value=[]):
                        with patch("packages.backend.app.services.integrity.check_orphaned_recurring", return_value=[]):
                            with patch("packages.backend.app.services.integrity.check_balance_consistency", return_value=[]):
                                result = run_integrity_check(1)
        assert result["summary"]["by_severity"]["warning"] == 1
        assert result["summary"]["by_severity"]["info"] == 1

    def test_checked_at_is_today(self):
        with patch("packages.backend.app.services.integrity.check_duplicate_expenses", return_value=[]):
            with patch("packages.backend.app.services.integrity.check_missing_categories", return_value=[]):
                with patch("packages.backend.app.services.integrity.check_large_amounts", return_value=[]):
                    with patch("packages.backend.app.services.integrity.check_future_dates", return_value=[]):
                        with patch("packages.backend.app.services.integrity.check_orphaned_recurring", return_value=[]):
                            with patch("packages.backend.app.services.integrity.check_balance_consistency", return_value=[]):
                                result = run_integrity_check(1)
        assert result["checked_at"] == str(date.today())


class TestReconciliationSummary:
    def test_structure_is_correct(self):
        with patch("packages.backend.app.services.integrity._get_monthly_net") as mock_net:
            mock_net.return_value = {"income": 50000, "expenses": 30000, "net": 20000}
            result = get_reconciliation_summary(1, 3)
        assert "months" in result
        assert "totals" in result
        assert "period_months" in result
        assert len(result["months"]) == 3

    def test_totals_are_sum_of_months(self):
        with patch("packages.backend.app.services.integrity._get_monthly_net") as mock_net:
            mock_net.return_value = {"income": 50000, "expenses": 30000, "net": 20000}
            result = get_reconciliation_summary(1, 3)
        assert result["totals"]["income"] == 150000
        assert result["totals"]["expenses"] == 90000
        assert result["totals"]["net"] == 60000

    def test_each_month_has_required_fields(self):
        with patch("packages.backend.app.services.integrity._get_monthly_net") as mock_net:
            mock_net.return_value = {"income": 1000, "expenses": 800, "net": 200}
            result = get_reconciliation_summary(1, 2)
        for m in result["months"]:
            assert "month" in m
            assert "income" in m
            assert "expenses" in m
            assert "net" in m

