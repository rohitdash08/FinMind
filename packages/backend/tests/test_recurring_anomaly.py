"""
Tests for recurring transaction anomaly detection (#108).
"""

import pytest
import socket
from decimal import Decimal
from datetime import date, timedelta

from app.services.recurring_anomaly import (
    RecurringConfig,
    ExpenseRecord,
    AnomalyAlert,
    detect_amount_anomalies,
    detect_missing_anomalies,
    detect_frequency_anomalies,
    analyze_recurring_expense,
    batch_analyze,
    anomaly_summary,
)


def _config(id=1, amount="100.00", cadence="MONTHLY", active=True):
    return RecurringConfig(
        id=id, expected_amount=Decimal(amount), cadence=cadence, active=active
    )


def _expense(id, amount, days_ago=0, rid=1):
    return ExpenseRecord(
        id=id,
        amount=Decimal(amount),
        date=date.today() - timedelta(days=days_ago),
        recurring_id=rid,
    )


def _redis_available():
    try:
        s = socket.create_connection(("localhost", 6379), timeout=0.5)
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(), reason="Redis not available"
)


# ─── Amount anomaly tests ─────────────────────────────────────────────────────

class TestDetectAmountAnomalies:
    def test_no_anomaly_within_threshold(self):
        cfg = _config(amount="100.00")
        expenses = [_expense(i, "100.00", days_ago=i*30) for i in range(5, 0, -1)]
        alerts = detect_amount_anomalies(cfg, expenses)
        assert alerts == []

    def test_small_deviation_no_alert(self):
        cfg = _config(amount="100.00")
        expenses = [
            _expense(1, "100.00", days_ago=90),
            _expense(2, "100.00", days_ago=60),
            _expense(3, "100.00", days_ago=30),
            _expense(4, "115.00"),  # 15% up — under threshold
        ]
        alerts = detect_amount_anomalies(cfg, expenses)
        assert alerts == []

    def test_medium_deviation_triggers_alert(self):
        cfg = _config(amount="100.00")
        expenses = [
            _expense(1, "100.00", days_ago=90),
            _expense(2, "100.00", days_ago=60),
            _expense(3, "100.00", days_ago=30),
            _expense(4, "130.00"),  # 30% up — above 20% threshold
        ]
        alerts = detect_amount_anomalies(cfg, expenses)
        assert len(alerts) == 1
        assert alerts[0].anomaly_type == "amount"
        assert alerts[0].severity in ("medium", "high")

    def test_critical_deviation_triggers_critical(self):
        cfg = _config(amount="100.00")
        expenses = [
            _expense(1, "100.00", days_ago=90),
            _expense(2, "100.00", days_ago=60),
            _expense(3, "100.00", days_ago=30),
            _expense(4, "200.00"),  # 100% up — critical
        ]
        alerts = detect_amount_anomalies(cfg, expenses)
        assert len(alerts) == 1
        assert alerts[0].severity == "critical"

    def test_empty_expenses_returns_no_alert(self):
        cfg = _config()
        assert detect_amount_anomalies(cfg, []) == []

    def test_single_expense_uses_expected_as_baseline(self):
        cfg = _config(amount="100.00")
        expenses = [_expense(1, "200.00")]  # 100% over expected
        alerts = detect_amount_anomalies(cfg, expenses)
        assert len(alerts) == 1
        assert alerts[0].severity == "critical"


# ─── Missing anomaly tests ────────────────────────────────────────────────────

class TestDetectMissingAnomalies:
    def test_no_anomaly_when_on_time(self):
        cfg = _config(cadence="MONTHLY")
        expenses = [_expense(1, "100.00", days_ago=28)]  # within 30 day window
        alerts = detect_missing_anomalies(cfg, expenses)
        assert alerts == []

    def test_detects_overdue_monthly(self):
        cfg = _config(cadence="MONTHLY")
        expenses = [_expense(1, "100.00", days_ago=40)]  # 10 days overdue
        alerts = detect_missing_anomalies(cfg, expenses)
        assert len(alerts) == 1
        assert alerts[0].anomaly_type == "missing"

    def test_detects_overdue_weekly(self):
        cfg = _config(cadence="WEEKLY")
        expenses = [_expense(1, "50.00", days_ago=14)]  # 7 days overdue
        alerts = detect_missing_anomalies(cfg, expenses)
        assert len(alerts) == 1

    def test_inactive_config_no_alert(self):
        cfg = _config(active=False, cadence="MONTHLY")
        expenses = [_expense(1, "100.00", days_ago=60)]
        alerts = detect_missing_anomalies(cfg, expenses)
        assert alerts == []

    def test_no_expenses_returns_empty(self):
        cfg = _config(cadence="MONTHLY")
        assert detect_missing_anomalies(cfg, []) == []


# ─── Frequency anomaly tests ──────────────────────────────────────────────────

class TestDetectFrequencyAnomalies:
    def test_normal_frequency_no_alert(self):
        cfg = _config(cadence="MONTHLY")
        expenses = [_expense(1, "100.00", days_ago=15)]  # 1 in 30 days = expected
        alerts = detect_frequency_anomalies(cfg, expenses)
        assert alerts == []

    def test_too_many_triggers_alert(self):
        cfg = _config(cadence="MONTHLY")
        # 3 charges in 30 days when only 1 expected
        expenses = [_expense(i, "100.00", days_ago=i*7) for i in range(1, 4)]
        alerts = detect_frequency_anomalies(cfg, expenses)
        assert len(alerts) == 1
        assert alerts[0].anomaly_type == "frequency"
        assert alerts[0].severity == "high"

    def test_weekly_normal_frequency(self):
        cfg = _config(cadence="WEEKLY")
        # 4-5 weekly expenses in 30 days = normal
        expenses = [_expense(i, "50.00", days_ago=i*7) for i in range(1, 5)]
        alerts = detect_frequency_anomalies(cfg, expenses)
        assert alerts == []

    def test_empty_expenses_no_alert(self):
        cfg = _config(cadence="MONTHLY")
        assert detect_frequency_anomalies(cfg, []) == []


# ─── Full analysis tests ──────────────────────────────────────────────────────

class TestAnalyzeRecurringExpense:
    def test_no_anomalies_clean_history(self):
        cfg = _config(amount="100.00", cadence="MONTHLY")
        expenses = [
            _expense(i, "100.00", days_ago=(5-i)*30)
            for i in range(1, 5)
        ]
        alerts = analyze_recurring_expense(cfg, expenses)
        assert alerts == []

    def test_combined_anomalies_detected(self):
        cfg = _config(amount="100.00", cadence="MONTHLY")
        # Old history normal, then large amount spike
        expenses = [
            _expense(1, "100.00", days_ago=90),
            _expense(2, "100.00", days_ago=60),
            _expense(3, "100.00", days_ago=30),
            _expense(4, "250.00"),  # critical amount anomaly
        ]
        alerts = analyze_recurring_expense(cfg, expenses)
        types = {a.anomaly_type for a in alerts}
        assert "amount" in types

    def test_inactive_config_returns_empty(self):
        cfg = _config(active=False)
        expenses = [_expense(1, "100.00", days_ago=40)]
        assert analyze_recurring_expense(cfg, expenses) == []


# ─── Batch analysis tests ─────────────────────────────────────────────────────

class TestBatchAnalyze:
    def test_returns_only_configs_with_anomalies(self):
        configs = [
            _config(id=1, amount="100.00"),  # clean
            _config(id=2, amount="50.00"),   # will have anomaly
        ]
        expenses_by_id = {
            1: [_expense(i, "100.00", days_ago=i*30, rid=1) for i in range(1, 5)],
            2: [
                _expense(10, "50.00", days_ago=90, rid=2),
                _expense(11, "50.00", days_ago=60, rid=2),
                _expense(12, "50.00", days_ago=30, rid=2),
                _expense(13, "200.00", rid=2),  # anomaly
            ],
        }
        result = batch_analyze(configs, expenses_by_id)
        assert 1 not in result   # no anomalies for config 1
        assert 2 in result       # anomaly for config 2


# ─── Summary tests ────────────────────────────────────────────────────────────

class TestAnomalySummary:
    def test_empty_list(self):
        s = anomaly_summary([])
        assert s["total"] == 0
        assert s["has_critical"] is False

    def test_counts_correctly(self):
        alerts = [
            AnomalyAlert(1, "amount", "critical", "msg"),
            AnomalyAlert(2, "missing", "high", "msg"),
            AnomalyAlert(3, "frequency", "medium", "msg"),
        ]
        s = anomaly_summary(alerts)
        assert s["total"] == 3
        assert s["has_critical"] is True
        assert s["by_type"]["amount"] == 1
        assert s["by_severity"]["critical"] == 1


# ─── API tests ────────────────────────────────────────────────────────────────

@requires_redis
class TestRecurringAnomalyAPI:
    def test_list_requires_auth(self, client):
        r = client.get("/recurring/anomalies")
        assert r.status_code == 401

    def test_detail_requires_auth(self, client):
        r = client.get("/recurring/anomalies/1")
        assert r.status_code == 401

    def test_list_returns_json(self, client, auth_header):
        r = client.get("/recurring/anomalies", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "anomalies" in data
        assert "summary" in data

    def test_nonexistent_recurring_returns_404(self, client, auth_header):
        r = client.get("/recurring/anomalies/99999", headers=auth_header)
        assert r.status_code == 404

    def test_thresholds_endpoint(self, client, auth_header):
        r = client.get("/recurring/anomalies/thresholds", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "amount_deviation_threshold" in data
        assert "amount_large_deviation" in data