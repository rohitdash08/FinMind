"""
Tests for Savings Opportunity Detection Engine (#119)
"""
import pytest
import socket
from decimal import Decimal
from datetime import date, timedelta

from app.services.savings_opportunity import (
    detect_savings_opportunities,
    _get_benchmark_ratio,
    _is_essential,
    _is_discretionary,
    CATEGORY_BENCHMARKS,
    ESSENTIAL_KEYWORDS,
    DISCRETIONARY_KEYWORDS,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _redis_available() -> bool:
    try:
        s = socket.create_connection(("localhost", 6379), timeout=0.5)
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(), reason="Redis not available"
)


# ── Unit tests (no DB / no auth needed) ──────────────────────────────────────

class TestBenchmarkLogic:
    """Tests for category benchmark detection helpers."""

    def test_food_benchmark_ratio(self):
        assert _get_benchmark_ratio("food") == 0.15

    def test_entertainment_benchmark_ratio(self):
        assert _get_benchmark_ratio("Entertainment") == 0.05

    def test_dining_benchmark_ratio(self):
        assert _get_benchmark_ratio("dining") == 0.05

    def test_subscriptions_benchmark_ratio(self):
        assert _get_benchmark_ratio("subscriptions") == 0.05

    def test_shopping_benchmark_ratio(self):
        assert _get_benchmark_ratio("shopping") == 0.10

    def test_unknown_category_returns_none(self):
        assert _get_benchmark_ratio("Unknown XYZ Category") is None

    def test_empty_category_returns_none(self):
        assert _get_benchmark_ratio("") is None

    def test_partial_match_works(self):
        # "gym membership" should match "gym" keyword
        assert _get_benchmark_ratio("gym membership") == 0.02

    def test_case_insensitive_match(self):
        assert _get_benchmark_ratio("FOOD") == 0.15
        assert _get_benchmark_ratio("Entertainment") == 0.05


class TestEssentialDetection:
    """Tests for essential vs. non-essential detection."""

    def test_rent_is_essential(self):
        assert _is_essential("rent") is True

    def test_medical_insurance_is_essential(self):
        assert _is_essential("medical insurance") is True

    def test_electricity_is_essential(self):
        assert _is_essential("electricity bill") is True

    def test_groceries_is_essential(self):
        assert _is_essential("groceries") is True

    def test_education_is_essential(self):
        assert _is_essential("education fees") is True

    def test_netflix_is_not_essential(self):
        assert _is_essential("netflix") is False

    def test_entertainment_is_not_essential(self):
        assert _is_essential("entertainment") is False

    def test_dining_is_not_essential(self):
        assert _is_essential("dining out") is False

    def test_empty_category_not_essential(self):
        assert _is_essential("") is False


class TestDiscretionaryDetection:
    """Tests for discretionary category detection."""

    def test_entertainment_is_discretionary(self):
        assert _is_discretionary("entertainment") is True

    def test_dining_is_discretionary(self):
        assert _is_discretionary("dining") is True

    def test_netflix_is_discretionary(self):
        assert _is_discretionary("netflix") is True

    def test_gaming_is_discretionary(self):
        assert _is_discretionary("gaming") is True

    def test_shopping_is_discretionary(self):
        assert _is_discretionary("shopping") is True

    def test_vacation_is_discretionary(self):
        assert _is_discretionary("vacation") is True

    def test_groceries_not_discretionary(self):
        assert _is_discretionary("groceries") is False

    def test_rent_not_discretionary(self):
        assert _is_discretionary("rent") is False

    def test_empty_category_not_discretionary(self):
        assert _is_discretionary("") is False


class TestSavingsOpportunityDetection:
    """Tests for detect_savings_opportunities service function."""

    def test_empty_user_returns_empty_opportunities(self, app_fixture):
        """User with no expenses gets no opportunities."""
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="empty_detect@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = detect_savings_opportunities(user.id)

        assert result["opportunities"] == []
        assert result["total_potential_savings"] == 0.0
        assert result["monthly_spend_avg"] == 0.0

    def test_result_has_required_fields(self, app_fixture):
        """Result always contains all required fields."""
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="fields_detect@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = detect_savings_opportunities(user.id)

        required = [
            "opportunities",
            "total_potential_savings",
            "monthly_spend_avg",
            "total_spend_analyzed",
            "analysis_period_months",
            "summary",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_opportunities_sorted_by_savings(self, app_fixture):
        """Opportunities must always be sorted descending by savings."""
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="sort_detect@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            # Add high discretionary + high entertainment spending
            ent_cat = Category(user_id=user.id, name="Entertainment")
            din_cat = Category(user_id=user.id, name="Dining")
            db.session.add_all([ent_cat, din_cat])
            db.session.flush()

            for days_ago in range(0, 90, 10):
                db.session.add(Expense(
                    user_id=user.id,
                    category_id=ent_cat.id,
                    amount=Decimal("3000"),
                    currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=days_ago),
                ))
                db.session.add(Expense(
                    user_id=user.id,
                    category_id=din_cat.id,
                    amount=Decimal("2000"),
                    currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=days_ago),
                ))
            db.session.commit()
            result = detect_savings_opportunities(user.id)

        opps = result["opportunities"]
        savings = [o["potential_monthly_savings"] for o in opps]
        assert savings == sorted(savings, reverse=True)

    def test_potential_savings_non_negative(self, app_fixture):
        """All savings figures must be >= 0."""
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="nonneg_detect@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = detect_savings_opportunities(user.id)

        assert result["total_potential_savings"] >= 0
        for opp in result["opportunities"]:
            assert opp["potential_monthly_savings"] >= 0

    def test_analysis_period_months_correct(self, app_fixture):
        """analysis_period_months matches the requested months."""
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="period_detect@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = detect_savings_opportunities(user.id, months=6)

        assert result["analysis_period_months"] == 6

    def test_opportunity_type_values(self, app_fixture):
        """All opportunity types are from known set."""
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        valid_types = {
            "over_benchmark",
            "high_discretionary",
            "top_spender",
            "subscription_audit",
        }

        with app_fixture.app_context():
            user = User(
                email="types_detect@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            cat = Category(user_id=user.id, name="Entertainment")
            db.session.add(cat)
            db.session.flush()

            for days in range(0, 60, 15):
                db.session.add(Expense(
                    user_id=user.id,
                    category_id=cat.id,
                    amount=Decimal("5000"),
                    currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=days),
                ))
            db.session.commit()
            result = detect_savings_opportunities(user.id)

        for opp in result["opportunities"]:
            assert opp["type"] in valid_types

    def test_severity_values(self, app_fixture):
        """All severity values are valid."""
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="sev_detect@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = detect_savings_opportunities(user.id)

        valid = {"high", "medium", "low"}
        for opp in result["opportunities"]:
            assert opp["severity"] in valid


# ── API endpoint tests (require Redis) ───────────────────────────────────────

class TestSavingsOpportunitiesAPI:
    """HTTP endpoint tests - skipped if Redis unavailable."""

    @requires_redis
    def test_endpoint_returns_200(self, client, auth_header):
        resp = client.get("/insights/savings-opportunities", headers=auth_header)
        assert resp.status_code == 200

    @requires_redis
    def test_summary_endpoint_returns_200(self, client, auth_header):
        resp = client.get("/insights/savings-opportunities/summary", headers=auth_header)
        assert resp.status_code == 200

    @requires_redis
    def test_requires_authentication(self, client):
        resp = client.get("/insights/savings-opportunities")
        assert resp.status_code == 401

    @requires_redis
    def test_summary_requires_authentication(self, client):
        resp = client.get("/insights/savings-opportunities/summary")
        assert resp.status_code == 401

    @requires_redis
    def test_months_parameter_validation(self, client, auth_header):
        resp = client.get(
            "/insights/savings-opportunities?months=invalid",
            headers=auth_header
        )
        assert resp.status_code == 200

    @requires_redis
    def test_months_clamped_to_12(self, client, auth_header):
        resp = client.get(
            "/insights/savings-opportunities?months=99",
            headers=auth_header
        )
        assert resp.status_code == 200

    @requires_redis
    def test_custom_months_reflected(self, client, auth_header):
        resp = client.get(
            "/insights/savings-opportunities?months=6",
            headers=auth_header
        )
        data = resp.get_json()
        assert data["analysis_period_months"] == 6

    @requires_redis
    def test_summary_has_required_fields(self, client, auth_header):
        resp = client.get("/insights/savings-opportunities/summary", headers=auth_header)
        data = resp.get_json()
        assert "opportunity_count" in data
        assert "total_potential_savings" in data
        assert "summary" in data
        assert "monthly_spend_avg" in data
