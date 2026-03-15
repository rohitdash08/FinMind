"""Tests for auto-detect subscriptions feature (Issue #109).

Covers:
  - Merchant name normalization
  - Cadence detection from date patterns
  - Amount consistency scoring
  - Known service identification
  - Confidence computation
  - Full subscription detection pipeline
  - Subscription CRUD operations
  - Monthly cost summary calculation
  - API endpoint testing
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.models import Expense, DetectedSubscription
from app.services.subscription_detection import (
    normalize_merchant_name,
    _detect_cadence,
    _amount_consistency,
    _is_known_service,
    _compute_confidence,
    _estimate_next_date,
    detect_subscriptions_for_user,
    get_subscriptions,
    update_subscription_status,
    get_monthly_subscription_cost,
)
from app.extensions import db


# ─── Unit tests: normalization ──────────────────────────────────────────


class TestNormalizeMerchantName:
    def test_basic_lowercase(self):
        assert normalize_merchant_name("Netflix") == "netflix"

    def test_strips_whitespace(self):
        assert normalize_merchant_name("  Spotify  ") == "spotify"

    def test_removes_payment_prefix(self):
        assert normalize_merchant_name("Payment to Netflix") == "netflix"

    def test_removes_recurring_prefix(self):
        assert normalize_merchant_name("Recurring Payment Spotify") == "spotify"

    def test_removes_date_suffix(self):
        assert normalize_merchant_name("Netflix Jan 2024") == "netflix"
        assert normalize_merchant_name("Spotify Feb") == "spotify"

    def test_removes_reference_numbers(self):
        assert normalize_merchant_name("Netflix #12345") == "netflix"
        assert normalize_merchant_name("Spotify ref678") == "spotify"

    def test_collapses_whitespace(self):
        assert normalize_merchant_name("Amazon   Prime") == "amazon prime"

    def test_empty_string(self):
        assert normalize_merchant_name("") == ""

    def test_none_handling(self):
        assert normalize_merchant_name(None) == ""


# ─── Unit tests: cadence detection ──────────────────────────────────────


class TestDetectCadence:
    def test_monthly_cadence(self):
        dates = [date(2024, m, 15) for m in range(1, 7)]
        cadence, score = _detect_cadence(dates)
        assert cadence == "MONTHLY"
        assert score > 0.5

    def test_weekly_cadence(self):
        start = date(2024, 1, 1)
        dates = [start + timedelta(weeks=i) for i in range(8)]
        cadence, score = _detect_cadence(dates)
        assert cadence == "WEEKLY"
        assert score > 0.5

    def test_yearly_cadence(self):
        dates = [date(2020 + i, 3, 15) for i in range(4)]
        cadence, score = _detect_cadence(dates)
        assert cadence == "YEARLY"
        assert score > 0.5

    def test_single_date_returns_monthly(self):
        cadence, score = _detect_cadence([date(2024, 1, 1)])
        assert cadence == "MONTHLY"
        assert score == 0.0


# ─── Unit tests: amount consistency ─────────────────────────────────────


class TestAmountConsistency:
    def test_identical_amounts(self):
        amounts = [Decimal("9.99")] * 5
        assert _amount_consistency(amounts) == 1.0

    def test_varying_amounts(self):
        amounts = [Decimal("9.99"), Decimal("15.00"), Decimal("9.99")]
        score = _amount_consistency(amounts)
        assert 0.0 < score < 1.0

    def test_single_amount(self):
        assert _amount_consistency([Decimal("10.00")]) == 1.0

    def test_empty_list(self):
        assert _amount_consistency([]) == 1.0


# ─── Unit tests: known service detection ────────────────────────────────


class TestIsKnownService:
    @pytest.mark.parametrize(
        "name",
        ["Netflix", "spotify", "Amazon Prime", "Google One", "adobe", "GitHub"],
    )
    def test_known_services(self, name):
        assert _is_known_service(name) is True

    def test_unknown_service(self):
        assert _is_known_service("random local shop") is False


# ─── Unit tests: confidence computation ─────────────────────────────────


class TestComputeConfidence:
    def test_high_confidence(self):
        score = _compute_confidence(
            occurrence_count=12,
            amount_consistency=1.0,
            interval_regularity=0.95,
            is_known=True,
        )
        assert score >= 0.85

    def test_low_confidence(self):
        score = _compute_confidence(
            occurrence_count=2,
            amount_consistency=0.3,
            interval_regularity=0.2,
            is_known=False,
        )
        assert score < 0.5

    def test_known_service_boost(self):
        without = _compute_confidence(3, 0.8, 0.8, False)
        with_known = _compute_confidence(3, 0.8, 0.8, True)
        assert with_known > without

    def test_score_clamped(self):
        score = _compute_confidence(100, 1.0, 1.0, True)
        assert score <= 1.0
        assert score >= 0.0


# ─── Unit tests: next date estimation ───────────────────────────────────


class TestEstimateNextDate:
    def test_monthly(self):
        result = _estimate_next_date(date(2024, 1, 15), "MONTHLY")
        assert result == date(2024, 2, 14)

    def test_weekly(self):
        result = _estimate_next_date(date(2024, 1, 1), "WEEKLY")
        assert result == date(2024, 1, 8)

    def test_yearly(self):
        result = _estimate_next_date(date(2024, 1, 1), "YEARLY")
        assert result == date(2024, 12, 31)  # 365 days from Jan 1


# ─── Integration tests: detection pipeline ──────────────────────────────


class TestDetectSubscriptions:
    def _create_expenses(self, user_id, merchant, dates, amount=9.99):
        for d in dates:
            exp = Expense(
                user_id=user_id,
                amount=Decimal(str(amount)),
                currency="INR",
                expense_type="EXPENSE",
                notes=merchant,
                spent_at=d,
            )
            db.session.add(exp)
        db.session.commit()

    def test_detects_monthly_subscription(self, app_fixture):
        with app_fixture.app_context():
            dates = [date(2024, m, 15) for m in range(1, 7)]
            self._create_expenses(1, "Netflix", dates)
            results = detect_subscriptions_for_user(1)
            assert len(results) >= 1
            netflix = [r for r in results if "netflix" in r["normalized_name"]]
            assert len(netflix) == 1
            assert netflix[0]["cadence"] == "MONTHLY"
            assert netflix[0]["occurrence_count"] == 6
            assert netflix[0]["confidence"] > 0.5

    def test_detects_weekly_subscription(self, app_fixture):
        with app_fixture.app_context():
            start = date(2024, 1, 1)
            dates = [start + timedelta(weeks=i) for i in range(8)]
            self._create_expenses(1, "Gym Membership", dates, amount=25.00)
            results = detect_subscriptions_for_user(1)
            gym = [r for r in results if "gym" in r["normalized_name"]]
            assert len(gym) == 1
            assert gym[0]["cadence"] == "WEEKLY"

    def test_ignores_single_occurrence(self, app_fixture):
        with app_fixture.app_context():
            self._create_expenses(1, "One-time purchase", [date(2024, 1, 15)])
            results = detect_subscriptions_for_user(1)
            single = [r for r in results if "one-time" in r["normalized_name"]]
            assert len(single) == 0

    def test_updates_existing_detection(self, app_fixture):
        with app_fixture.app_context():
            dates = [date(2024, m, 15) for m in range(1, 5)]
            self._create_expenses(1, "Spotify", dates)
            results1 = detect_subscriptions_for_user(1)
            assert len(results1) >= 1

            # Add more months
            more_dates = [date(2024, m, 15) for m in range(5, 7)]
            self._create_expenses(1, "Spotify", more_dates)
            results2 = detect_subscriptions_for_user(1)
            spotify = [r for r in results2 if "spotify" in r["normalized_name"]]
            assert spotify[0]["occurrence_count"] == 6

    def test_no_expenses_returns_empty(self, app_fixture):
        with app_fixture.app_context():
            results = detect_subscriptions_for_user(999)
            assert results == []


# ─── Integration tests: status management ───────────────────────────────


class TestSubscriptionStatus:
    def _seed_subscription(self, user_id=1):
        sub = DetectedSubscription(
            user_id=user_id,
            merchant_name="Netflix",
            normalized_name="netflix",
            amount=Decimal("9.99"),
            currency="INR",
            cadence="MONTHLY",
            confidence=Decimal("0.85"),
            first_seen=date(2024, 1, 15),
            last_seen=date(2024, 6, 15),
            next_expected=date(2024, 7, 15),
            occurrence_count=6,
            status="detected",
            is_active=True,
        )
        db.session.add(sub)
        db.session.commit()
        return sub.id

    def test_confirm_subscription(self, app_fixture):
        with app_fixture.app_context():
            sub_id = self._seed_subscription()
            result = update_subscription_status(1, sub_id, "confirmed")
            assert result is not None
            assert result["status"] == "confirmed"
            assert result["is_active"] is True

    def test_dismiss_subscription(self, app_fixture):
        with app_fixture.app_context():
            sub_id = self._seed_subscription()
            result = update_subscription_status(1, sub_id, "dismissed")
            assert result is not None
            assert result["status"] == "dismissed"
            assert result["is_active"] is False

    def test_invalid_status(self, app_fixture):
        with app_fixture.app_context():
            sub_id = self._seed_subscription()
            result = update_subscription_status(1, sub_id, "invalid")
            assert result is None

    def test_not_found(self, app_fixture):
        with app_fixture.app_context():
            result = update_subscription_status(1, 999, "confirmed")
            assert result is None


# ─── Integration tests: get subscriptions ────────────────────────────────


class TestGetSubscriptions:
    def test_get_active_only(self, app_fixture):
        with app_fixture.app_context():
            for name, active in [("netflix", True), ("hulu", False)]:
                sub = DetectedSubscription(
                    user_id=1, merchant_name=name, normalized_name=name,
                    amount=Decimal("9.99"), currency="INR", cadence="MONTHLY",
                    confidence=Decimal("0.85"), first_seen=date(2024, 1, 1),
                    last_seen=date(2024, 6, 1), occurrence_count=6,
                    status="detected", is_active=active,
                )
                db.session.add(sub)
            db.session.commit()
            active = get_subscriptions(1, active_only=True)
            assert len(active) == 1
            assert active[0]["normalized_name"] == "netflix"

    def test_get_all(self, app_fixture):
        with app_fixture.app_context():
            for name, active in [("netflix", True), ("hulu", False)]:
                sub = DetectedSubscription(
                    user_id=1, merchant_name=name, normalized_name=name,
                    amount=Decimal("9.99"), currency="INR", cadence="MONTHLY",
                    confidence=Decimal("0.85"), first_seen=date(2024, 1, 1),
                    last_seen=date(2024, 6, 1), occurrence_count=6,
                    status="detected", is_active=active,
                )
                db.session.add(sub)
            db.session.commit()
            all_subs = get_subscriptions(1, active_only=False)
            assert len(all_subs) == 2


# ─── Integration tests: monthly cost ────────────────────────────────────


class TestMonthlyCost:
    def test_calculates_monthly_cost(self, app_fixture):
        with app_fixture.app_context():
            for name, amount, cadence in [
                ("netflix", "15.99", "MONTHLY"),
                ("spotify", "9.99", "MONTHLY"),
                ("gym", "25.00", "WEEKLY"),
            ]:
                sub = DetectedSubscription(
                    user_id=1, merchant_name=name, normalized_name=name,
                    amount=Decimal(amount), currency="INR", cadence=cadence,
                    confidence=Decimal("0.85"), first_seen=date(2024, 1, 1),
                    last_seen=date(2024, 6, 1), occurrence_count=6,
                    status="confirmed", is_active=True,
                )
                db.session.add(sub)
            db.session.commit()
            summary = get_monthly_subscription_cost(1)
            assert summary["subscription_count"] == 3
            # 15.99 + 9.99 + (25 * 4.33) = ~134.23
            assert summary["monthly_total"] > 100
            assert summary["yearly_total"] > 1000

    def test_empty_subscriptions(self, app_fixture):
        with app_fixture.app_context():
            summary = get_monthly_subscription_cost(999)
            assert summary["monthly_total"] == 0.0
            assert summary["subscription_count"] == 0


# ─── API tests ──────────────────────────────────────────────────────────


class TestSubscriptionAPI:
    def test_scan_endpoint(self, client, auth_header):
        # Create some recurring expenses first
        for m in range(1, 5):
            client.post("/expenses", json={
                "amount": 9.99,
                "description": "Netflix",
                "date": f"2024-{m:02d}-15",
            }, headers=auth_header)

        resp = client.post("/subscriptions/scan", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "detected_count" in data
        assert "subscriptions" in data

    def test_list_endpoint(self, client, auth_header):
        resp = client.get("/subscriptions", headers=auth_header)
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_summary_endpoint(self, client, auth_header):
        resp = client.get("/subscriptions/summary", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "monthly_total" in data
        assert "yearly_total" in data

    def test_get_subscription_not_found(self, client, auth_header):
        resp = client.get("/subscriptions/999", headers=auth_header)
        assert resp.status_code == 404

    def test_update_status_invalid(self, client, auth_header):
        resp = client.patch(
            "/subscriptions/1/status",
            json={"status": "invalid"},
            headers=auth_header,
        )
        assert resp.status_code == 400

    def test_update_status_not_found(self, client, auth_header):
        resp = client.patch(
            "/subscriptions/999/status",
            json={"status": "confirmed"},
            headers=auth_header,
        )
        assert resp.status_code == 404

    def test_list_with_active_filter(self, client, auth_header):
        resp = client.get(
            "/subscriptions?active_only=false", headers=auth_header
        )
        assert resp.status_code == 200

    def test_scan_detects_and_lists(self, client, auth_header):
        # Create monthly Netflix charges
        for m in range(1, 7):
            client.post("/expenses", json={
                "amount": 15.99,
                "description": "Netflix",
                "date": f"2024-{m:02d}-15",
            }, headers=auth_header)

        # Scan
        resp = client.post("/subscriptions/scan", headers=auth_header)
        assert resp.status_code == 200
        scan_data = resp.get_json()
        assert scan_data["detected_count"] >= 1

        # List
        resp = client.get("/subscriptions", headers=auth_header)
        assert resp.status_code == 200
        subs = resp.get_json()
        assert len(subs) >= 1
        netflix = [s for s in subs if "netflix" in s["normalized_name"]]
        assert len(netflix) >= 1

    def test_unauthorized_access(self, client):
        resp = client.get("/subscriptions")
        assert resp.status_code == 401
