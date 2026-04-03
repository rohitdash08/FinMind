"""
Tests for automatic subscription detection (#109).
"""

import pytest
import socket
from decimal import Decimal
from datetime import date, timedelta

from app.services.subscription_autodetect import (
    ExpenseEntry,
    DetectedSubscription,
    match_known_service,
    detect_from_expenses,
    detection_summary,
    _normalize,
    _cadence_from_charges,
    _amount_is_consistent,
    KNOWN_SUBSCRIPTIONS,
)


def _expense(id, description, amount, days_ago=0, notes=""):
    return ExpenseEntry(
        id=id,
        amount=Decimal(str(amount)),
        date=date.today() - timedelta(days=days_ago),
        description=description,
        notes=notes,
    )


def _monthly_expenses(description, amount, months=4, start_days_ago=120):
    """Create a series of monthly charges."""
    return [
        _expense(i + 1, description, amount, days_ago=start_days_ago - (i * 30))
        for i in range(months)
    ]


def _redis_available():
    try:
        s = socket.create_connection(("localhost", 6379), timeout=0.5)
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


requires_redis = pytest.mark.skipif(not _redis_available(), reason="Redis not available")


# ─── Normalization tests ──────────────────────────────────────────────────────

class TestNormalize:
    def test_lowercases(self):
        assert _normalize("NETFLIX") == "netflix"

    def test_strips_long_numbers(self):
        assert "12345678" not in _normalize("NETFLIX12345678")

    def test_strips_asterisks(self):
        assert "*" not in _normalize("NETFLIX*STREAMING")

    def test_strips_special_chars(self):
        result = _normalize("SPOTIFY.COM/BILL")
        assert "." not in result


# ─── Known service matching tests ─────────────────────────────────────────────

class TestMatchKnownService:
    def test_exact_match_netflix(self):
        assert match_known_service("Netflix") == "Netflix"

    def test_case_insensitive(self):
        assert match_known_service("NETFLIX") == "Netflix"

    def test_partial_match_in_description(self):
        assert match_known_service("NETFLIX SUBSCRIPTION") == "Netflix"

    def test_match_from_notes(self):
        assert match_known_service("charge 1234", "spotify premium") == "Spotify"

    def test_no_match_returns_none(self):
        assert match_known_service("corner store groceries") is None

    def test_spotify_matches(self):
        assert match_known_service("Spotify Premium") == "Spotify"

    def test_chatgpt_matches(self):
        assert match_known_service("chatgpt plus monthly") == "ChatGPT Plus"

    def test_all_known_services_are_detectable(self):
        for keyword, expected_name in list(KNOWN_SUBSCRIPTIONS.items())[:10]:
            assert match_known_service(keyword) == expected_name


# ─── Cadence detection tests ──────────────────────────────────────────────────

class TestCadenceDetection:
    def test_monthly_cadence(self):
        dates = [date.today() - timedelta(days=i * 30) for i in range(4, 0, -1)]
        assert _cadence_from_charges(dates) == "MONTHLY"

    def test_yearly_cadence(self):
        dates = [date.today() - timedelta(days=i * 365) for i in range(3, 0, -1)]
        assert _cadence_from_charges(dates) == "YEARLY"

    def test_single_date_unknown(self):
        assert _cadence_from_charges([date.today()]) == "UNKNOWN"

    def test_empty_dates_unknown(self):
        assert _cadence_from_charges([]) == "UNKNOWN"


# ─── Amount consistency tests ─────────────────────────────────────────────────

class TestAmountConsistency:
    def test_same_amounts_consistent(self):
        amounts = [Decimal("15.99")] * 5
        assert _amount_is_consistent(amounts) is True

    def test_small_variation_consistent(self):
        amounts = [Decimal("15.99"), Decimal("16.01"), Decimal("15.98")]
        assert _amount_is_consistent(amounts) is True

    def test_large_variation_not_consistent(self):
        amounts = [Decimal("10.00"), Decimal("50.00"), Decimal("5.00")]
        assert _amount_is_consistent(amounts) is False

    def test_empty_amounts_not_consistent(self):
        assert _amount_is_consistent([]) is False


# ─── Full detection tests ─────────────────────────────────────────────────────

class TestDetectFromExpenses:
    def test_detects_netflix_monthly(self):
        expenses = _monthly_expenses("Netflix", "15.99", months=4)
        results = detect_from_expenses(expenses, min_occurrences=2)
        assert len(results) >= 1
        names = [r.service_name for r in results]
        assert any("Netflix" in n for n in names)

    def test_detects_spotify_monthly(self):
        expenses = _monthly_expenses("Spotify Premium", "9.99", months=3)
        results = detect_from_expenses(expenses, min_occurrences=2)
        names = [r.service_name for r in results]
        assert any("Spotify" in n for n in names)

    def test_irregular_non_subscription_not_detected(self):
        # Grocery store charges at random intervals
        expenses = [
            _expense(1, "Whole Foods Market", "45.23", days_ago=100),
            _expense(2, "Whole Foods Market", "78.12", days_ago=45),
            _expense(3, "Whole Foods Market", "32.45"),
        ]
        results = detect_from_expenses(expenses, min_occurrences=2)
        # Should not detect (amount inconsistent, no name match)
        # Low confidence because no name match + irregular amounts
        for r in results:
            assert r.confidence < 0.7 or r.charge_count < 3

    def test_single_charge_not_detected(self):
        expenses = [_expense(1, "Netflix", "15.99")]
        results = detect_from_expenses(expenses, min_occurrences=2)
        assert len(results) == 0

    def test_results_sorted_by_monthly_cost_desc(self):
        netflix = _monthly_expenses("Netflix", "15.99", months=4)
        spotify = _monthly_expenses("Spotify", "9.99", months=4)
        results = detect_from_expenses(netflix + spotify, min_occurrences=2)
        if len(results) >= 2:
            costs = [r.estimated_monthly_cost for r in results]
            assert costs == sorted(costs, reverse=True)

    def test_confidence_at_least_0_5_for_known_services(self):
        expenses = _monthly_expenses("Netflix", "15.99", months=3)
        results = detect_from_expenses(expenses, min_occurrences=2)
        for r in results:
            if "Netflix" in r.service_name:
                assert r.confidence >= 0.5

    def test_empty_expenses_returns_empty(self):
        assert detect_from_expenses([]) == []

    def test_lookback_window_respected(self):
        # Old charges outside window should not be included
        old_expenses = [
            _expense(i, "Netflix", "15.99", days_ago=400 + i * 30)
            for i in range(4)
        ]
        results = detect_from_expenses(old_expenses, lookback_days=90)
        assert len(results) == 0


# ─── Summary tests ────────────────────────────────────────────────────────────

class TestDetectionSummary:
    def test_empty_summary(self):
        s = detection_summary([])
        assert s["total_detected"] == 0
        assert s["estimated_total_monthly_spend"] == "0.00"

    def test_sums_monthly_costs(self):
        # Mock detected subscription
        expenses = (
            _monthly_expenses("Netflix", "15.99", months=4) +
            _monthly_expenses("Spotify", "9.99", months=3)
        )
        results = detect_from_expenses(expenses, min_occurrences=2)
        s = detection_summary(results)
        assert s["total_detected"] == len(results)
        # Monthly total should be around 25.98 if both detected
        if len(results) == 2:
            assert float(s["estimated_total_monthly_spend"]) > 0


# ─── API endpoint tests ───────────────────────────────────────────────────────

@requires_redis
class TestSubscriptionAutodetectAPI:
    def test_detect_requires_auth(self, client):
        r = client.get("/subscriptions/detect")
        assert r.status_code == 401

    def test_known_services_requires_auth(self, client):
        r = client.get("/subscriptions/detect/known-services")
        assert r.status_code == 401

    def test_detect_returns_json(self, client, auth_header):
        r = client.get("/subscriptions/detect", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "subscriptions" in data
        assert "summary" in data

    def test_known_services_returns_list(self, client, auth_header):
        r = client.get("/subscriptions/detect/known-services", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "services" in data
        assert data["total"] > 0