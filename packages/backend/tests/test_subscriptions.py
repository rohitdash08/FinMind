import pytest
from decimal import Decimal
from datetime import date, timedelta
from app.models import Expense
from app.extensions import db

def _get_uid(auth_header: dict) -> int:
    """Extract user ID from JWT."""
    import base64, json
    token = auth_header["Authorization"].split(" ")[1]
    payload_b64 = token.split(".")[1]
    # Add padding
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    payload = json.loads(base64.b64decode(payload_b64))
    return int(payload.get("sub", payload.get("identity", 0)))

def _insert_expense(app_fixture, uid: int, amount: float, notes: str, days_ago: int, expense_type: str = "EXPENSE"):
    with app_fixture.app_context():
        exp = Expense(
            user_id=uid,
            amount=Decimal(str(amount)),
            currency="INR",
            expense_type=expense_type,
            notes=notes,
            spent_at=date.today() - timedelta(days=days_ago)
        )
        db.session.add(exp)
        db.session.commit()

class TestSubscriptionDetectionEndpoint:
    """Tests for GET /subscriptions/detected."""

    def test_requires_auth(self, client):
        r = client.get("/subscriptions/detected")
        assert r.status_code == 401

    def test_empty_history_returns_empty(self, client, auth_header):
        r = client.get("/subscriptions/detected", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["subscriptions"] == []
        assert data["total_monthly_estimate"] == 0.0
        assert data["analysis_period_months"] == 6

    def test_custom_months_param(self, client, auth_header):
        r = client.get("/subscriptions/detected?months=3", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["analysis_period_months"] == 3

    def test_invalid_months_defaults_to_6(self, client, auth_header):
        r = client.get("/subscriptions/detected?months=abc", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["analysis_period_months"] == 6

    def test_detects_keyword_match_monthly(self, client, auth_header, app_fixture):
        """Netflix keyword + monthly cadence = detected subscription."""
        uid = _get_uid(auth_header)
        for i in [0, 30, 60]:
            _insert_expense(app_fixture, uid, 15.99, "netflix", days_ago=i)

        r = client.get("/subscriptions/detected", headers=auth_header)
        assert r.status_code == 200
        subs = r.get_json()["subscriptions"]
        netflix = next((s for s in subs if "netflix" in s["merchant"]), None)
        assert netflix is not None
        assert netflix["occurrences"] == 3
        assert netflix["keyword_match"] is True

    def test_detects_monthly_cadence_no_keyword(self, client, auth_header, app_fixture):
        """Regular monthly charges without keyword detected via cadence."""
        uid = _get_uid(auth_header)
        for i in [0, 30, 60, 90]:
            _insert_expense(app_fixture, uid, 9.99, "SomeCustomService", days_ago=i)

        r = client.get("/subscriptions/detected", headers=auth_header)
        assert r.status_code == 200
        subs = r.get_json()["subscriptions"]
        custom = next((s for s in subs if "somecustomservice" in s["merchant"]), None)
        assert custom is not None
        assert custom["cadence"] == "monthly"
        assert custom["confidence"] == "medium"

    def test_ignores_single_occurrence(self, client, auth_header, app_fixture):
        """One-time charges should not be flagged as subscriptions."""
        uid = _get_uid(auth_header)
        _insert_expense(app_fixture, uid, 99.99, "one-time-purchase", days_ago=5)

        r = client.get("/subscriptions/detected", headers=auth_header)
        assert r.status_code == 200
        subs = r.get_json()["subscriptions"]
        one_time = next((s for s in subs if "one-time" in s["merchant"]), None)
        assert one_time is None

    def test_response_schema(self, client, auth_header, app_fixture):
        """Response includes all required fields."""
        uid = _get_uid(auth_header)
        for i in [0, 30, 60]:
            _insert_expense(app_fixture, uid, 9.99, "spotify", days_ago=i)

        r = client.get("/subscriptions/detected", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "subscriptions" in data
        assert "total_monthly_estimate" in data
        assert "analysis_period_months" in data

        if data["subscriptions"]:
            sub = data["subscriptions"][0]
            for field in ["merchant", "cadence", "occurrences", "average_amount",
                          "currency", "monthly_estimate", "confidence",
                          "keyword_match", "last_charge", "first_charge"]:
                assert field in sub, f"Missing field: {field}"

    def test_high_confidence_keyword_plus_cadence(self, client, auth_header, app_fixture):
        """Both keyword + cadence = high confidence."""
        uid = _get_uid(auth_header)
        for i in [0, 30, 60]:
            _insert_expense(app_fixture, uid, 12.99, "spotify premium", days_ago=i)

        r = client.get("/subscriptions/detected", headers=auth_header)
        subs = r.get_json()["subscriptions"]
        spotify = next((s for s in subs if "spotify" in s["merchant"]), None)
        assert spotify is not None
        assert spotify["confidence"] == "high"

    def test_total_monthly_estimate_is_sum_of_subscriptions(self, client, auth_header, app_fixture):
        """total_monthly_estimate = sum of individual monthly_estimate values."""
        uid = _get_uid(auth_header)
        for i in [0, 30, 60]:
            _insert_expense(app_fixture, uid, 10.00, "netflix", days_ago=i)
        for i in [0, 30, 60]:
            _insert_expense(app_fixture, uid, 5.00, "spotify", days_ago=i)

        r = client.get("/subscriptions/detected", headers=auth_header)
        data = r.get_json()
        subs = data["subscriptions"]
        computed = sum(s["monthly_estimate"] for s in subs)
        assert abs(data["total_monthly_estimate"] - computed) < 0.01

    def test_sorted_by_monthly_estimate_desc(self, client, auth_header, app_fixture):
        """Results sorted by monthly_estimate descending."""
        uid = _get_uid(auth_header)
        for i in [0, 30, 60]:
            _insert_expense(app_fixture, uid, 50.00, "expensive-service", days_ago=i)
        for i in [0, 30, 60]:
            _insert_expense(app_fixture, uid, 5.00, "cheap-service", days_ago=i)

        r = client.get("/subscriptions/detected", headers=auth_header)
        subs = r.get_json()["subscriptions"]
        if len(subs) >= 2:
            estimates = [s["monthly_estimate"] for s in subs]
            assert estimates == sorted(estimates, reverse=True)

    def test_income_type_excluded(self, client, auth_header, app_fixture):
        """INCOME type transactions should not be treated as subscriptions."""
        uid = _get_uid(auth_header)
        for i in [0, 30, 60]:
            _insert_expense(app_fixture, uid, 15.99, "netflix", days_ago=i, expense_type="INCOME")

        r = client.get("/subscriptions/detected", headers=auth_header)
        subs = r.get_json()["subscriptions"]
        netflix = next((s for s in subs if s["merchant"] == "netflix"), None)
        assert netflix is None

    def test_expenses_outside_period_excluded(self, client, auth_header, app_fixture):
        """Expenses outside analysis window should not be included."""
        uid = _get_uid(auth_header)
        # Add expenses 8 months ago (outside 6-month window)
        for i in [240, 270, 300]:
            _insert_expense(app_fixture, uid, 9.99, "old-service", days_ago=i)

        r = client.get("/subscriptions/detected?months=6", headers=auth_header)
        subs = r.get_json()["subscriptions"]
        old = next((s for s in subs if "old-service" in s["merchant"]), None)
        assert old is None
