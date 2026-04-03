"""
Tests for Spending Trend Heatmap Visualization (#116)
"""
import pytest
import socket
from decimal import Decimal
from datetime import date, timedelta

from app.services.spending_heatmap import (
    get_spending_heatmap,
    _intensity,
    _week_number,
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


class TestIntensityCalculation:
    """Tests for intensity level calculation."""

    def test_zero_is_level_0(self):
        assert _intensity(0, 100) == "0"

    def test_max_zero_is_level_0(self):
        assert _intensity(50, 0) == "0"

    def test_low_25_percent_is_level_1(self):
        assert _intensity(20, 100) == "1"

    def test_medium_50_percent_is_level_2(self):
        assert _intensity(40, 100) == "2"

    def test_high_75_percent_is_level_3(self):
        assert _intensity(60, 100) == "3"

    def test_max_is_level_4(self):
        assert _intensity(100, 100) == "4"

    def test_intensity_returns_string(self):
        assert isinstance(_intensity(50, 100), str)


class TestWeekNumber:
    """Tests for ISO week number calculation."""

    def test_jan_first_2026(self):
        # Jan 1, 2026 is week 1 of 2026
        result = _week_number(date(2026, 1, 1))
        assert isinstance(result, int)
        assert 1 <= result <= 53

    def test_week_number_is_integer(self):
        result = _week_number(date(2026, 3, 15))
        assert isinstance(result, int)


class TestSpendingHeatmapService:
    """Tests for get_spending_heatmap service."""

    def test_empty_user_returns_empty_heatmap(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="empty_heatmap@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_heatmap(user.id)

        assert result["cells"] == []
        assert result["total_spend"] == 0

    def test_daily_view_has_correct_structure(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="daily_heatmap@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_heatmap(user.id, view="daily")

        assert result["view"] == "daily"

    def test_weekday_view_has_7_days(self, app_fixture):
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="weekday_heatmap@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            cat = Category(user_id=user.id, name="Shopping")
            db.session.add(cat)
            db.session.flush()

            for days_ago in range(0, 30, 3):
                db.session.add(Expense(
                    user_id=user.id, category_id=cat.id,
                    amount=Decimal("500"), currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=days_ago),
                ))
            db.session.commit()
            result = get_spending_heatmap(user.id, view="weekday")

        assert result["view"] == "weekday"
        assert len(result["cells"]) == 7

    def test_weekday_cells_have_required_fields(self, app_fixture):
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="wdfields_heatmap@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            cat = Category(user_id=user.id, name="Food")
            db.session.add(cat)
            db.session.flush()

            db.session.add(Expense(
                user_id=user.id, category_id=cat.id,
                amount=Decimal("100"), currency="INR",
                expense_type="EXPENSE",
                spent_at=date.today() - timedelta(days=1),
            ))
            db.session.commit()
            result = get_spending_heatmap(user.id, view="weekday")

        for cell in result["cells"]:
            assert "day_of_week" in cell
            assert "day_name" in cell
            assert "total" in cell
            assert "average" in cell
            assert "intensity" in cell

    def test_monthly_view_returns_months(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="monthly_heatmap@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_heatmap(user.id, view="monthly", months=3)

        assert result["view"] == "monthly"

    def test_daily_cells_have_required_fields(self, app_fixture):
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="dailyfields_heatmap@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            cat = Category(user_id=user.id, name="Food")
            db.session.add(cat)
            db.session.flush()

            db.session.add(Expense(
                user_id=user.id, category_id=cat.id,
                amount=Decimal("1000"), currency="INR",
                expense_type="EXPENSE",
                spent_at=date.today() - timedelta(days=1),
            ))
            db.session.commit()
            result = get_spending_heatmap(user.id, view="daily", months=1)

        assert len(result["cells"]) > 0
        for cell in result["cells"]:
            assert "date" in cell
            assert "day_of_week" in cell
            assert "amount" in cell
            assert "intensity" in cell

    def test_intensity_values_valid(self, app_fixture):
        from app.models import User, Category, Expense
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="intensity_heatmap@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.flush()

            cat = Category(user_id=user.id, name="Food")
            db.session.add(cat)
            db.session.flush()

            for days in range(1, 10):
                db.session.add(Expense(
                    user_id=user.id, category_id=cat.id,
                    amount=Decimal(str(days * 100)),
                    currency="INR", expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=days),
                ))
            db.session.commit()
            result = get_spending_heatmap(user.id, view="daily", months=1)

        valid_intensities = {"0", "1", "2", "3", "4"}
        for cell in result["cells"]:
            assert cell["intensity"] in valid_intensities

    def test_months_clamped_to_1_12(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="clamp_heatmap@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_heatmap(user.id, months=99)

        assert result["months_analyzed"] <= 12

    def test_max_value_non_negative(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="maxval_heatmap@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = get_spending_heatmap(user.id)

        assert result.get("total_spend", 0) >= 0


class TestSpendingHeatmapAPI:
    """HTTP endpoint tests."""

    @requires_redis
    def test_heatmap_returns_200(self, client, auth_header):
        resp = client.get("/insights/spending-heatmap", headers=auth_header)
        assert resp.status_code == 200

    @requires_redis
    def test_requires_authentication(self, client):
        resp = client.get("/insights/spending-heatmap")
        assert resp.status_code == 401

    @requires_redis
    def test_daily_view_parameter(self, client, auth_header):
        resp = client.get("/insights/spending-heatmap?view=daily", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["view"] == "daily"

    @requires_redis
    def test_weekday_view_parameter(self, client, auth_header):
        resp = client.get("/insights/spending-heatmap?view=weekday", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["view"] == "weekday"

    @requires_redis
    def test_monthly_view_parameter(self, client, auth_header):
        resp = client.get("/insights/spending-heatmap?view=monthly", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["view"] == "monthly"

    @requires_redis
    def test_invalid_view_defaults_to_daily(self, client, auth_header):
        resp = client.get("/insights/spending-heatmap?view=invalid", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["view"] == "daily"

    @requires_redis
    def test_months_parameter(self, client, auth_header):
        resp = client.get("/insights/spending-heatmap?months=3", headers=auth_header)
        assert resp.status_code == 200
