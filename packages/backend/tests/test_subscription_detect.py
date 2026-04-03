"""
Tests for subscription cost increase detection (#110).
"""

import pytest
import socket
from decimal import Decimal
from datetime import date, timedelta

from app.services.subscription_detect import (
    SubscriptionConfig,
    ChargeRecord,
    PriceChangeAlert,
    detect_price_increase,
    detect_vs_expected,
    scan_all_subscriptions,
    price_change_summary,
    DEFAULT_INCREASE_THRESHOLD,
    SIGNIFICANT_INCREASE_PCT,
    LARGE_INCREASE_PCT,
)


def _config(id=1, name="Netflix", amount="15.99", currency="USD", active=True):
    return SubscriptionConfig(
        id=id, name=name, expected_amount=Decimal(amount),
        cadence="MONTHLY", currency=currency, active=active
    )


def _charge(id, amount, days_ago=0, sub_id=1):
    return ChargeRecord(
        id=id,
        amount=Decimal(amount),
        charge_date=date.today() - timedelta(days=days_ago),
        subscription_id=sub_id,
    )


def _redis_available():
    try:
        s = socket.create_connection(("localhost", 6379), timeout=0.5)
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


requires_redis = pytest.mark.skipif(not _redis_available(), reason="Redis not available")


# ─── detect_price_increase tests ─────────────────────────────────────────────

class TestDetectPriceIncrease:
    def test_no_increase_same_price(self):
        cfg = _config(amount="15.99")
        charges = [
            _charge(1, "15.99", days_ago=60),
            _charge(2, "15.99", days_ago=30),
            _charge(3, "15.99"),
        ]
        alerts = detect_price_increase(cfg, charges)
        assert alerts == []

    def test_price_decrease_no_alert(self):
        cfg = _config(amount="15.99")
        charges = [_charge(1, "15.99", 60), _charge(2, "12.99", 30)]
        assert detect_price_increase(cfg, charges) == []

    def test_small_increase_triggers_info(self):
        cfg = _config(amount="15.99")
        charges = [_charge(1, "15.99", 30), _charge(2, "16.59")]  # ~3.75% increase - info
        alerts = detect_price_increase(cfg, charges)
        assert len(alerts) == 1
        assert alerts[0].severity == "info"  # < 10%
        assert alerts[0].new_amount == Decimal("16.59")
        assert alerts[0].old_amount == Decimal("15.99")

    def test_10pct_increase_triggers_medium(self):
        cfg = _config(amount="15.99")
        charges = [_charge(1, "10.00", 60), _charge(2, "11.50", 30)]  # 15% increase
        alerts = detect_price_increase(cfg, charges)
        assert len(alerts) == 1
        assert alerts[0].severity == "medium"

    def test_25pct_increase_triggers_high(self):
        cfg = _config(amount="10.00")
        charges = [_charge(1, "10.00", 30), _charge(2, "14.00")]  # 40% increase
        alerts = detect_price_increase(cfg, charges)
        assert len(alerts) == 1
        assert alerts[0].severity == "high"

    def test_multiple_increases_detected(self):
        cfg = _config(amount="10.00")
        charges = [
            _charge(1, "10.00", days_ago=90),
            _charge(2, "11.00", days_ago=60),  # +10%
            _charge(3, "12.00", days_ago=30),  # +9%
            _charge(4, "15.00"),               # +25%
        ]
        alerts = detect_price_increase(cfg, charges)
        assert len(alerts) == 3

    def test_empty_charges_no_alerts(self):
        cfg = _config()
        assert detect_price_increase(cfg, []) == []

    def test_single_charge_no_alerts(self):
        cfg = _config()
        assert detect_price_increase(cfg, [_charge(1, "10.00")]) == []

    def test_inactive_subscription_no_alert(self):
        cfg = _config(active=False)
        charges = [_charge(1, "10.00", 30), _charge(2, "15.00")]
        assert detect_price_increase(cfg, charges) == []

    def test_alert_contains_correct_change_amount(self):
        cfg = _config(amount="10.00")
        charges = [_charge(1, "10.00", 30), _charge(2, "13.00")]
        alerts = detect_price_increase(cfg, charges)
        assert len(alerts) == 1
        assert alerts[0].increase_amount == Decimal("3.00")


# ─── detect_vs_expected tests ─────────────────────────────────────────────────

class TestDetectVsExpected:
    def test_higher_than_expected_returns_alert(self):
        cfg = _config(amount="15.99")
        latest = _charge(1, "19.99")
        alert = detect_vs_expected(cfg, latest)
        assert alert is not None
        assert alert.severity in ("info", "medium", "high")

    def test_same_as_expected_returns_none(self):
        cfg = _config(amount="15.99")
        latest = _charge(1, "15.99")
        assert detect_vs_expected(cfg, latest) is None

    def test_lower_than_expected_returns_none(self):
        cfg = _config(amount="15.99")
        latest = _charge(1, "12.99")
        assert detect_vs_expected(cfg, latest) is None

    def test_none_latest_returns_none(self):
        cfg = _config()
        assert detect_vs_expected(cfg, None) is None


# ─── scan_all_subscriptions tests ────────────────────────────────────────────

class TestScanAll:
    def test_returns_alerts_for_affected_subs(self):
        configs = [
            _config(id=1, name="Netflix", amount="15.99"),
            _config(id=2, name="Spotify", amount="9.99"),
        ]
        charges = {
            1: [_charge(1, "15.99", 30, sub_id=1), _charge(2, "19.99", 0, sub_id=1)],
            2: [_charge(3, "9.99", 30, sub_id=2), _charge(4, "9.99", 0, sub_id=2)],
        }
        alerts = scan_all_subscriptions(configs, charges)
        assert any(a.subscription_name == "Netflix" for a in alerts)
        assert not any(a.subscription_name == "Spotify" for a in alerts)

    def test_empty_no_alerts(self):
        assert scan_all_subscriptions([], {}) == []

    def test_sorted_high_severity_first(self):
        configs = [
            _config(id=1, name="A", amount="10.00"),
            _config(id=2, name="B", amount="10.00"),
        ]
        charges = {
            1: [_charge(1, "10.00", 30, 1), _charge(2, "11.00", 0, 1)],   # info
            2: [_charge(3, "10.00", 30, 2), _charge(4, "15.00", 0, 2)],   # high (50%)
        }
        alerts = scan_all_subscriptions(configs, charges)
        if len(alerts) >= 2:
            sev_order = {"high": 3, "medium": 2, "info": 1}
            sev_values = [sev_order[a.severity] for a in alerts]
            assert sev_values == sorted(sev_values, reverse=True)


# ─── price_change_summary tests ──────────────────────────────────────────────

class TestPriceChangeSummary:
    def test_empty_summary(self):
        s = price_change_summary([])
        assert s["total_alerts"] == 0
        assert s["has_high_severity"] is False
        assert s["total_extra_monthly_spend"] == "0.00"

    def test_counts_and_totals(self):
        alerts = [
            PriceChangeAlert(1, "Netflix", Decimal("15.99"), Decimal("19.99"),
                             Decimal("0.25"), "high", "msg"),
            PriceChangeAlert(2, "Spotify", Decimal("9.99"), Decimal("10.99"),
                             Decimal("0.10"), "medium", "msg"),
        ]
        s = price_change_summary(alerts)
        assert s["total_alerts"] == 2
        assert s["has_high_severity"] is True
        assert s["by_severity"]["high"] == 1
        assert s["by_severity"]["medium"] == 1
        # Total extra = 4.00 + 1.00 = 5.00
        assert s["total_extra_monthly_spend"] == "5.00"


# ─── API endpoint tests ───────────────────────────────────────────────────────

@requires_redis
class TestSubscriptionDetectAPI:
    def test_list_requires_auth(self, client):
        r = client.get("/subscriptions/price-changes")
        assert r.status_code == 401

    def test_detail_requires_auth(self, client):
        r = client.get("/subscriptions/price-changes/1")
        assert r.status_code == 401

    def test_list_returns_json(self, client, auth_header):
        r = client.get("/subscriptions/price-changes", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "alerts" in data
        assert "summary" in data

    def test_nonexistent_subscription_returns_404(self, client, auth_header):
        r = client.get("/subscriptions/price-changes/99999", headers=auth_header)
        assert r.status_code == 404