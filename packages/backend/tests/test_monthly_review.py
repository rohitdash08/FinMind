"""
Tests for Guided Monthly Financial Review Flow (#102)
"""
import pytest
import socket
from decimal import Decimal
from datetime import date, timedelta

from app.services.monthly_review import (
    generate_monthly_review,
    _get_month_range,
    _get_prev_month,
    REVIEW_STEPS,
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


class TestMonthHelpers:
    """Tests for month utility functions."""

    def test_get_month_range_january(self):
        start, end = _get_month_range("2026-01")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 2, 1)

    def test_get_month_range_december(self):
        start, end = _get_month_range("2026-12")
        assert start == date(2026, 12, 1)
        assert end == date(2027, 1, 1)

    def test_get_month_range_march(self):
        start, end = _get_month_range("2026-03")
        assert start == date(2026, 3, 1)
        assert end == date(2026, 4, 1)

    def test_get_prev_month_january(self):
        assert _get_prev_month("2026-01") == "2025-12"

    def test_get_prev_month_december(self):
        assert _get_prev_month("2026-12") == "2026-11"

    def test_get_prev_month_march(self):
        assert _get_prev_month("2026-03") == "2026-02"

    def test_review_steps_count(self):
        assert len(REVIEW_STEPS) == 6

    def test_review_steps_have_required_fields(self):
        for step in REVIEW_STEPS:
            assert "id" in step
            assert "title" in step
            assert "description" in step
            assert "order" in step

    def test_review_steps_ordered_correctly(self):
        orders = [s["order"] for s in REVIEW_STEPS]
        assert orders == sorted(orders)

    def test_review_step_ids_unique(self):
        ids = [s["id"] for s in REVIEW_STEPS]
        assert len(ids) == len(set(ids))


class TestMonthlyReviewService:
    """Tests for generate_monthly_review service."""

    def test_empty_user_returns_structured_response(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="empty_review@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = generate_monthly_review(user.id, month="2026-03")

        assert "month" in result
        assert "review_steps" in result
        assert "progress" in result
        assert "summary" in result

    def test_returns_correct_month(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="month_review@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = generate_monthly_review(user.id, month="2026-03")

        assert result["month"] == "2026-03"

    def test_returns_six_steps(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="steps_review@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = generate_monthly_review(user.id, month="2026-03")

        assert len(result["review_steps"]) == 6

    def test_each_step_has_required_fields(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="stepfields_review@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = generate_monthly_review(user.id, month="2026-03")

        for step in result["review_steps"]:
            assert "id" in step
            assert "title" in step
            assert "data" in step
            assert "insight" in step
            assert "status" in step

    def test_progress_has_correct_structure(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="progress_review@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = generate_monthly_review(user.id, month="2026-03")

        progress = result["progress"]
        assert "completed" in progress
        assert "total" in progress
        assert "pct" in progress
        assert progress["total"] == 6
        assert 0 <= progress["pct"] <= 100

    def test_summary_has_required_fields(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="summary_review@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = generate_monthly_review(user.id, month="2026-03")

        summary = result["summary"]
        for field in ["total_spend", "total_income", "net_position",
                      "expense_categories", "action_items"]:
            assert field in summary

    def test_defaults_to_last_month(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        today = date.today()
        expected = (
            f"{today.year}-{today.month - 1:02d}"
            if today.month > 1
            else f"{today.year - 1}-12"
        )

        with app_fixture.app_context():
            user = User(
                email="default_review@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = generate_monthly_review(user.id)  # No month param

        assert result["month"] == expected

    def test_step_status_is_valid(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        valid_statuses = {"complete", "no_data", "no_income_data"}

        with app_fixture.app_context():
            user = User(
                email="status_review@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = generate_monthly_review(user.id, month="2026-03")

        for step in result["review_steps"]:
            assert step["status"] in valid_statuses

    def test_action_items_have_priority_and_action(self, app_fixture):
        from app.models import User
        from app.extensions import db
        from werkzeug.security import generate_password_hash

        with app_fixture.app_context():
            user = User(
                email="actions_review@finmind.io",
                password_hash=generate_password_hash("pass"),
            )
            db.session.add(user)
            db.session.commit()
            result = generate_monthly_review(user.id, month="2026-03")

        action_step = next(s for s in result["review_steps"] if s["id"] == "action_items")
        for action in action_step["data"]["actions"]:
            assert "priority" in action
            assert "action" in action
            assert action["priority"] in ("high", "medium", "low")


class TestMonthlyReviewAPI:
    """HTTP endpoint tests."""

    @requires_redis
    def test_review_endpoint_returns_200(self, client, auth_header):
        resp = client.get("/insights/monthly-review?month=2026-03", headers=auth_header)
        assert resp.status_code == 200

    @requires_redis
    def test_review_requires_auth(self, client):
        resp = client.get("/insights/monthly-review")
        assert resp.status_code == 401

    def test_steps_endpoint_no_auth_needed(self, client):
        resp = client.get("/insights/monthly-review/steps")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "steps" in data
        assert data["total"] == 6

    @requires_redis
    def test_default_month_used_when_not_specified(self, client, auth_header):
        resp = client.get("/insights/monthly-review", headers=auth_header)
        assert resp.status_code == 200

    @requires_redis
    def test_specific_month_in_response(self, client, auth_header):
        resp = client.get("/insights/monthly-review?month=2026-02", headers=auth_header)
        data = resp.get_json()
        assert data["month"] == "2026-02"
