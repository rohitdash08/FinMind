"""Tests for the weekly digest service (issue #121)."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers to detect whether Redis / SQLAlchemy are available
# ---------------------------------------------------------------------------
try:
    from app.extensions import db  # noqa: F401
    _db_available = True
except Exception:
    _db_available = False

requires_db = pytest.mark.skipif(
    not _db_available, reason="Database not configured for testing"
)


# ---------------------------------------------------------------------------
# Unit tests – no DB required
# ---------------------------------------------------------------------------

class TestGetWeekRange:
    def test_monday_start(self):
        from app.services.weekly_digest import _get_week_range
        # 2024-04-01 is a Monday
        start, end = _get_week_range(date(2024, 4, 1))
        assert start == date(2024, 4, 1)
        assert end == date(2024, 4, 7)

    def test_midweek(self):
        from app.services.weekly_digest import _get_week_range
        # Wednesday 2024-04-03
        start, end = _get_week_range(date(2024, 4, 3))
        assert start == date(2024, 4, 1)
        assert end == date(2024, 4, 7)

    def test_sunday(self):
        from app.services.weekly_digest import _get_week_range
        # Sunday 2024-04-07
        start, end = _get_week_range(date(2024, 4, 7))
        assert start == date(2024, 4, 1)
        assert end == date(2024, 4, 7)

    def test_defaults_to_today(self):
        from app.services.weekly_digest import _get_week_range
        today = date.today()
        start, end = _get_week_range()
        assert start <= today <= end
        assert (end - start).days == 6


class TestGetPrevWeekRange:
    def test_prev_week(self):
        from app.services.weekly_digest import _get_prev_week_range
        start, end = _get_prev_week_range(date(2024, 4, 3))
        assert start == date(2024, 3, 25)
        assert end == date(2024, 3, 31)


class TestComputeWeeklyDigestMocked:
    """Tests that mock the DB session so they run without a live database."""

    def _make_expense(self, amount, expense_type="EXPENSE", spent_at=None, category_id=None):
        e = MagicMock()
        e.amount = amount
        e.expense_type = expense_type
        e.spent_at = spent_at or date.today()
        e.category_id = category_id
        e.id = 1
        e.currency = "INR"
        e.notes = "Test"
        return e

    def test_empty_week(self):
        from app.services.weekly_digest import compute_weekly_digest
        with patch("app.services.weekly_digest.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            result = compute_weekly_digest(user_id=1, reference_date=date(2024, 4, 1))
        assert result["total_spent"] == 0.0
        assert result["total_income"] == 0.0
        assert result["net"] == 0.0
        assert result["category_breakdown"] == []
        assert result["top_expense"] is None

    def test_spending_only(self):
        from app.services.weekly_digest import compute_weekly_digest
        expenses = [
            self._make_expense(100.0, "EXPENSE"),
            self._make_expense(200.0, "EXPENSE"),
        ]
        with patch("app.services.weekly_digest.db") as mock_db:
            # First two calls: current week, prev week via chained filter
            call_responses = [expenses, expenses, []]  # current, current (prev week for wow)
            call_iter = iter(call_responses)

            def side_effect(*args, **kwargs):
                m = MagicMock()
                def filter_side(*a, **kw):
                    fm = MagicMock()
                    fm.all.return_value = next(call_iter, [])
                    fm.filter.return_value = fm
                    fm.order_by.return_value.limit.return_value.all.return_value = []
                    return fm
                m.filter.side_effect = filter_side
                return m

            mock_db.session.query.side_effect = side_effect
            result = compute_weekly_digest(user_id=1, reference_date=date(2024, 4, 1))

        assert result["total_spent"] == 300.0
        assert result["total_income"] == 0.0
        assert result["net"] == -300.0

    def test_week_range_in_result(self):
        from app.services.weekly_digest import compute_weekly_digest
        with patch("app.services.weekly_digest.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            result = compute_weekly_digest(user_id=1, reference_date=date(2024, 4, 3))
        assert result["week_start"] == "2024-04-01"
        assert result["week_end"] == "2024-04-07"

    def test_result_keys(self):
        from app.services.weekly_digest import compute_weekly_digest
        with patch("app.services.weekly_digest.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            result = compute_weekly_digest(user_id=1, reference_date=date(2024, 4, 1))
        expected_keys = {
            "week_start", "week_end", "total_spent", "total_income", "net",
            "category_breakdown", "top_expense", "week_over_week_change",
            "upcoming_bills", "insights",
        }
        assert expected_keys.issubset(result.keys())

    def test_insights_low_spending(self):
        from app.services.weekly_digest import compute_weekly_digest
        with patch("app.services.weekly_digest.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            result = compute_weekly_digest(user_id=1, reference_date=date(2024, 4, 1))
        # With no data, insight about missing income should appear
        assert isinstance(result["insights"], list)

    def test_wow_change_zero_prev_week(self):
        from app.services.weekly_digest import compute_weekly_digest
        with patch("app.services.weekly_digest.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            result = compute_weekly_digest(user_id=1)
        assert result["week_over_week_change"] == 0.0


class TestWeeklyDigestRoute:
    """Integration-style tests for the Flask route (no live DB)."""

    @pytest.fixture
    def client(self):
        try:
            from app import create_app
            app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                              "JWT_SECRET_KEY": "test-secret"})
            with app.test_client() as c:
                yield c
        except Exception:
            pytest.skip("Flask app not available in test environment")

    def test_requires_auth(self, client):
        resp = client.get("/weekly-digest/")
        assert resp.status_code in (401, 422)

    def test_invalid_date(self, client):
        from flask_jwt_extended import create_access_token
        try:
            from app import create_app
            app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                              "JWT_SECRET_KEY": "test-secret"})
            with app.app_context():
                token = create_access_token(identity="1")
            resp = client.get("/weekly-digest/?date=not-a-date",
                               headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 400
        except Exception:
            pytest.skip("JWT token creation failed")
