"""
Tests for Essential vs Discretionary Spending Breakdown (#120)
"""
import pytest
import socket
from decimal import Decimal
from datetime import date, timedelta

from app.services.spending_classification import (
    get_spending_breakdown,
    _classify_category,
    ESSENTIAL_CATEGORIES,
    DISCRETIONARY_CATEGORIES,
)


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


class TestCategoryClassification:
    """Unit tests for category classification logic."""

    def test_rent_is_essential(self):
        assert _classify_category("rent") == "essential"

    def test_groceries_is_essential(self):
        assert _classify_category("groceries") == "essential"

    def test_medical_is_essential(self):
        assert _classify_category("medical") == "essential"

    def test_electricity_is_essential(self):
        assert _classify_category("electricity") == "essential"

    def test_education_is_essential(self):
        assert _classify_category("education") == "essential"

    def test_insurance_is_essential(self):
        assert _classify_category("insurance") == "essential"

    def test_loan_is_essential(self):
        assert _classify_category("loan emi") == "essential"

    def test_entertainment_is_discretionary(self):
        assert _classify_category("entertainment") == "discretionary"

    def test_dining_is_discretionary(self):
        assert _classify_category("dining") == "discretionary"

    def test_shopping_is_discretionary(self):
        assert _classify_category("shopping") == "discretionary"

    def test_netflix_is_discretionary(self):
        assert _classify_category("netflix") == "discretionary"

    def test_gaming_is_discretionary(self):
        assert _classify_category("gaming") == "discretionary"

    def test_gym_is_discretionary(self):
        assert _classify_category("gym") == "discretionary"

    def test_vacation_is_discretionary(self):
        assert _classify_category("vacation") == "discretionary"

    def test_none_category_defaults_to_discretionary(self):
        assert _classify_category(None) in ("discretionary", "mixed")

    def test_empty_category_defaults_to_discretionary(self):
        assert _classify_category("") in ("discretionary", "mixed")

    def test_case_insensitive_classification(self):
        assert _classify_category("RENT") == "essential"
        assert _classify_category("ENTERTAINMENT") == "discretionary"

    def test_partial_match_works(self):
        # "monthly rent payment" should classify as essential
        assert _classify_category("monthly rent payment") == "essential"
        # "dining at restaurant" should classify as discretionary
        assert _classify_category("dining at restaurant") == "discretionary"


class TestSpendingBreakdownService:
    """Tests for the get_spending_breakdown service function."""

    def test_empty_user_returns_zero_totals(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="empty_breakdown@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_breakdown(user.id)

        assert result["summary"]["total_spend"] == 0.0
        assert result["summary"]["essential_total"] == 0.0
        assert result["summary"]["discretionary_total"] == 0.0

    def test_result_has_required_structure(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="struct_breakdown@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_breakdown(user.id)

        assert "summary" in result
        assert "essential" in result
        assert "discretionary" in result
        assert "mixed" in result
        assert "insights" in result
        assert "period" in result

    def test_summary_contains_required_fields(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="fields_breakdown@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_breakdown(user.id)

        summary = result["summary"]
        for field in ["total_spend", "essential_total", "discretionary_total",
                      "essential_pct", "discretionary_pct"]:
            assert field in summary, f"Missing field: {field}"

    def test_percentages_sum_to_approximately_100(self, app_fixture):
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="pct_breakdown@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            rent_cat = Category(user_id=user.id, name="rent")
            ent_cat = Category(user_id=user.id, name="entertainment")
            db.session.add_all([rent_cat, ent_cat])
            db.session.flush()

            for days in [10, 20, 30]:
                db.session.add(Expense(
                    user_id=user.id, category_id=rent_cat.id,
                    amount=Decimal("10000"), currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=days),
                ))
                db.session.add(Expense(
                    user_id=user.id, category_id=ent_cat.id,
                    amount=Decimal("5000"), currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=days),
                ))
            db.session.commit()
            result = get_spending_breakdown(user.id)

        total_pct = result["summary"]["essential_pct"] + result["summary"]["discretionary_pct"]
        assert abs(total_pct - 100.0) < 1.0  # Allow 1% rounding error

    def test_essential_spending_classified_correctly(self, app_fixture):
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="ess_class@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            rent_cat = Category(user_id=user.id, name="rent")
            db.session.add(rent_cat)
            db.session.flush()

            db.session.add(Expense(
                user_id=user.id, category_id=rent_cat.id,
                amount=Decimal("20000"), currency="INR",
                expense_type="EXPENSE",
                spent_at=date.today() - timedelta(days=5),
            ))
            db.session.commit()
            result = get_spending_breakdown(user.id)

        assert result["essential"]["total"] > 0
        assert result["summary"]["essential_pct"] > 50

    def test_discretionary_spending_classified_correctly(self, app_fixture):
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="disc_class@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            ent_cat = Category(user_id=user.id, name="entertainment")
            db.session.add(ent_cat)
            db.session.flush()

            db.session.add(Expense(
                user_id=user.id, category_id=ent_cat.id,
                amount=Decimal("5000"), currency="INR",
                expense_type="EXPENSE",
                spent_at=date.today() - timedelta(days=5),
            ))
            db.session.commit()
            result = get_spending_breakdown(user.id)

        assert result["discretionary"]["total"] > 0

    def test_categories_list_contains_name_amount_pct(self, app_fixture):
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="cat_list@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            cat = Category(user_id=user.id, name="rent")
            db.session.add(cat)
            db.session.flush()

            db.session.add(Expense(
                user_id=user.id, category_id=cat.id,
                amount=Decimal("10000"), currency="INR",
                expense_type="EXPENSE",
                spent_at=date.today() - timedelta(days=5),
            ))
            db.session.commit()
            result = get_spending_breakdown(user.id)

        for cat_entry in result["essential"]["categories"]:
            assert "name" in cat_entry
            assert "amount" in cat_entry
            assert "pct" in cat_entry

    def test_insights_always_present(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="insights_breakdown@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_breakdown(user.id)

        assert isinstance(result["insights"], list)
        assert len(result["insights"]) > 0
        for insight in result["insights"]:
            assert "type" in insight
            assert "message" in insight

    def test_months_parameter_respected(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="months_breakdown@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_breakdown(user.id, months=6)

        assert result["period"]["months"] == 6

    def test_specific_month_parameter(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="specific_month@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_breakdown(user.id, month="2026-03")

        assert result["period"]["specific_month"] == "2026-03"


class TestSpendingBreakdownAPI:
    """HTTP endpoint tests - skipped if Redis unavailable."""

    @requires_redis
    def test_endpoint_returns_200(self, client, auth_header):
        resp = client.get("/insights/spending-breakdown", headers=auth_header)
        assert resp.status_code == 200

    @requires_redis
    def test_requires_authentication(self, client):
        resp = client.get("/insights/spending-breakdown")
        assert resp.status_code == 401

    @requires_redis
    def test_month_parameter_accepted(self, client, auth_header):
        resp = client.get(
            "/insights/spending-breakdown?month=2026-03",
            headers=auth_header
        )
        assert resp.status_code == 200

    @requires_redis
    def test_months_parameter_accepted(self, client, auth_header):
        resp = client.get(
            "/insights/spending-breakdown?months=6",
            headers=auth_header
        )
        assert resp.status_code == 200

    @requires_redis
    def test_response_has_summary(self, client, auth_header):
        resp = client.get("/insights/spending-breakdown", headers=auth_header)
        data = resp.get_json()
        assert "summary" in data
        assert "essential" in data
        assert "discretionary" in data

    @requires_redis
    def test_invalid_months_handled(self, client, auth_header):
        resp = client.get(
            "/insights/spending-breakdown?months=abc",
            headers=auth_header
        )
        assert resp.status_code == 200
