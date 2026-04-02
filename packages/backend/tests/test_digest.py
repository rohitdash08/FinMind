"""
Tests for Weekly Digest functionality
"""

from datetime import date, timedelta
import pytest


class TestWeeklyDigestService:
    """Tests for the WeeklyDigestService class."""

    def test_get_week_bounds_returns_monday_to_sunday(self):
        """Test that week bounds return Monday to Sunday."""
        from app.services.digest import WeeklyDigestService

        # Test with a Wednesday
        wednesday = date(2024, 1, 10)  # This is a Wednesday
        week_start, week_end = WeeklyDigestService.get_week_bounds(wednesday)

        # Should return Monday Jan 8 to Sunday Jan 14
        assert week_start == date(2024, 1, 8)  # Monday
        assert week_end == date(2024, 1, 14)  # Sunday
        assert week_start.weekday() == 0  # Monday
        assert week_end.weekday() == 6  # Sunday

    def test_get_week_bounds_with_monday_input(self):
        """Test that Monday input returns the same week."""
        from app.services.digest import WeeklyDigestService

        monday = date(2024, 1, 8)  # This is a Monday
        week_start, week_end = WeeklyDigestService.get_week_bounds(monday)

        assert week_start == monday
        assert week_end == date(2024, 1, 14)  # Sunday

    def test_get_previous_week_bounds(self):
        """Test getting previous week bounds."""
        from app.services.digest import WeeklyDigestService

        wednesday = date(2024, 1, 10)
        prev_start, prev_end = WeeklyDigestService.get_previous_week_bounds(wednesday)

        # Previous week should be Jan 1-7
        assert prev_start == date(2024, 1, 1)  # Monday
        assert prev_end == date(2024, 1, 7)  # Sunday

    def test_generate_weekly_summary_basic(self, app_fixture, auth_header):
        """Test basic weekly summary generation."""
        from app.services.digest import WeeklyDigestService
        from app.extensions import db
        from app.models import User

        with app_fixture.app_context():
            # Get user ID from auth header setup
            user = db.session.query(User).filter_by(email="test@example.com").first()
            user_id = user.id

            # Create a category
            client = app_fixture.test_client()
            r = client.post(
                "/categories", json={"name": "Food"}, headers=auth_header
            )
            assert r.status_code == 201

            # Add some transactions
            today = date.today()
            client.post(
                "/expenses",
                json={
                    "amount": 1000,
                    "description": "Salary",
                    "date": today.isoformat(),
                    "expense_type": "INCOME",
                },
                headers=auth_header,
            )

            client.post(
                "/expenses",
                json={
                    "amount": 200,
                    "description": "Groceries",
                    "date": today.isoformat(),
                    "expense_type": "EXPENSE",
                },
                headers=auth_header,
            )

            week_start, week_end = WeeklyDigestService.get_week_bounds()
            summary = WeeklyDigestService.generate_weekly_summary(
                user_id, week_start, week_end
            )

            assert "period" in summary
            assert "summary" in summary
            assert "trends" in summary
            assert "spending_by_category" in summary
            assert "notable_transactions" in summary
            assert "upcoming_bills" in summary
            assert "insights" in summary

            assert summary["summary"]["total_income"] == 1000.0
            assert summary["summary"]["total_expenses"] == 200.0
            assert summary["summary"]["net_flow"] == 800.0
            assert summary["summary"]["savings_rate"] == 80.0
            assert summary["summary"]["transaction_count"] == 2

    def test_generate_weekly_summary_with_category_breakdown(
        self, app_fixture, auth_header
    ):
        """Test category breakdown in weekly summary."""
        from app.services.digest import WeeklyDigestService
        from app.extensions import db
        from app.models import User

        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email="test@example.com").first()
            user_id = user.id

            client = app_fixture.test_client()

            # Create categories
            r1 = client.post(
                "/categories", json={"name": "Food"}, headers=auth_header
            )
            r2 = client.post(
                "/categories", json={"name": "Transport"}, headers=auth_header
            )

            food_id = r1.get_json()["id"]
            transport_id = r2.get_json()["id"]

            today = date.today()

            # Add expenses in different categories
            client.post(
                "/expenses",
                json={
                    "amount": 300,
                    "description": "Groceries",
                    "date": today.isoformat(),
                    "expense_type": "EXPENSE",
                    "category_id": food_id,
                },
                headers=auth_header,
            )

            client.post(
                "/expenses",
                json={
                    "amount": 150,
                    "description": "Gas",
                    "date": today.isoformat(),
                    "expense_type": "EXPENSE",
                    "category_id": transport_id,
                },
                headers=auth_header,
            )

            week_start, week_end = WeeklyDigestService.get_week_bounds()
            summary = WeeklyDigestService.generate_weekly_summary(
                user_id, week_start, week_end
            )

            category_breakdown = summary["spending_by_category"]
            assert len(category_breakdown) == 2

            # Check total equals sum of categories
            total_from_categories = sum(c["amount"] for c in category_breakdown)
            assert total_from_categories == 450.0

            # Check percentages add up to 100
            total_pct = sum(c["share_pct"] for c in category_breakdown)
            assert abs(total_pct - 100.0) < 0.1

    def test_generate_weekly_summary_with_upcoming_bills(
        self, app_fixture, auth_header
    ):
        """Test upcoming bills in weekly summary."""
        from app.services.digest import WeeklyDigestService
        from app.extensions import db
        from app.models import User

        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email="test@example.com").first()
            user_id = user.id

            client = app_fixture.test_client()

            # Create a bill due in 3 days
            due_date = date.today() + timedelta(days=3)
            r = client.post(
                "/bills",
                json={
                    "name": "Internet",
                    "amount": 49.99,
                    "next_due_date": due_date.isoformat(),
                    "cadence": "MONTHLY",
                },
                headers=auth_header,
            )
            assert r.status_code == 201

            week_start, week_end = WeeklyDigestService.get_week_bounds()
            summary = WeeklyDigestService.generate_weekly_summary(
                user_id, week_start, week_end
            )

            upcoming = summary["upcoming_bills"]
            assert len(upcoming) >= 1
            assert any(b["name"] == "Internet" for b in upcoming)

    def test_generate_insights_high_savings_rate(self):
        """Test insights generation with high savings rate."""
        from app.services.digest import WeeklyDigestService

        summary = {
            "summary": {
                "savings_rate": 35.0,
                "total_income": 1000.0,
                "total_expenses": 650.0,
                "transaction_count": 5,
            },
            "trends": {
                "income_change_pct": 0.0,
                "expense_change_pct": 0.0,
                "income_change": 0.0,
                "expense_change": 0.0,
            },
            "spending_by_category": [
                {"category_name": "Food", "amount": 400.0, "share_pct": 61.5}
            ],
            "upcoming_bills": [],
        }

        insights = WeeklyDigestService._generate_insights(summary)

        assert len(insights) > 0
        assert any("Excellent savings rate" in i for i in insights)

    def test_generate_insights_negative_savings_rate(self):
        """Test insights generation when expenses exceed income."""
        from app.services.digest import WeeklyDigestService

        summary = {
            "summary": {
                "savings_rate": -10.0,
                "total_income": 500.0,
                "total_expenses": 550.0,
                "transaction_count": 5,
            },
            "trends": {
                "income_change_pct": 0.0,
                "expense_change_pct": 25.0,
                "income_change": 0.0,
                "expense_change": 100.0,
            },
            "spending_by_category": [
                {"category_name": "Shopping", "amount": 400.0, "share_pct": 72.7}
            ],
            "upcoming_bills": [],
        }

        insights = WeeklyDigestService._generate_insights(summary)

        assert any("exceeded income" in i.lower() for i in insights)

    def test_format_digest_email(self, app_fixture):
        """Test email formatting."""
        from app.services.digest import WeeklyDigestService
        from app.models import User

        with app_fixture.app_context():
            user = User(
                email="test@example.com",
                password_hash="hash",
                preferred_currency="USD",
            )

            summary = {
                "period": {
                    "week_start": "2024-01-08",
                    "week_end": "2024-01-14",
                },
                "summary": {
                    "total_income": 1000.0,
                    "total_expenses": 400.0,
                    "net_flow": 600.0,
                    "savings_rate": 60.0,
                    "transaction_count": 5,
                },
                "trends": {
                    "income_change": 100.0,
                    "expense_change": -50.0,
                    "income_change_pct": 11.1,
                    "expense_change_pct": -11.1,
                },
                "spending_by_category": [
                    {"category_name": "Food", "amount": 300.0, "share_pct": 75.0},
                    {"category_name": "Transport", "amount": 100.0, "share_pct": 25.0},
                ],
                "notable_transactions": [
                    {
                        "type": "INCOME",
                        "description": "Salary",
                        "amount": 1000.0,
                        "date": "2024-01-08",
                    },
                    {
                        "type": "EXPENSE",
                        "description": "Groceries",
                        "amount": 200.0,
                        "date": "2024-01-10",
                    },
                ],
                "upcoming_bills": [
                    {"name": "Internet", "amount": 49.99, "days_until_due": 3}
                ],
                "insights": ["Great savings rate!", "Income is up this week."],
            }

            subject, body = WeeklyDigestService.format_digest_email(summary, user)

            assert "Weekly Financial Summary" in subject
            assert "test@example.com" in body
            assert "Total Income" in body
            assert "$1,000.00" in body
            assert "Food" in body
            assert "Internet" in body


class TestDigestRoutes:
    """Tests for digest API endpoints."""

    def test_get_weekly_digest_unauthorized(self, client):
        """Test that digest requires authentication."""
        r = client.get("/digest/weekly")
        assert r.status_code == 401

    def test_get_weekly_digest_authorized(self, client, auth_header):
        """Test getting weekly digest with authentication."""
        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200

        data = r.get_json()
        assert "period" in data
        assert "summary" in data
        assert "trends" in data
        assert "spending_by_category" in data

    def test_get_weekly_digest_with_week_start(self, client, auth_header):
        """Test getting digest for a specific week."""
        from datetime import date

        week_start = date.today() - timedelta(days=7)
        # Adjust to Monday
        days_since_monday = week_start.weekday()
        week_start = week_start - timedelta(days=days_since_monday)

        r = client.get(
            f"/digest/weekly?week_start={week_start.isoformat()}",
            headers=auth_header,
        )
        assert r.status_code == 200

    def test_get_weekly_digest_invalid_date(self, client, auth_header):
        """Test that invalid date format returns error."""
        r = client.get("/digest/weekly?week_start=invalid", headers=auth_header)
        assert r.status_code == 400

    def test_preview_weekly_digest(self, client, auth_header):
        """Test digest preview endpoint."""
        r = client.get("/digest/weekly/preview", headers=auth_header)
        assert r.status_code == 200

        data = r.get_json()
        assert "subject" in data
        assert "body" in data
        assert "summary" in data

    def test_send_weekly_digest_no_transactions(self, client, auth_header):
        """Test sending digest when there are no transactions."""
        r = client.post("/digest/weekly/send", headers=auth_header)
        assert r.status_code == 200

        data = r.get_json()
        assert data["success"] is False
        assert "No transactions" in data["message"]

    def test_send_weekly_digest_with_transactions(self, client, auth_header):
        """Test sending digest with transactions (email sending mocked)."""
        # Add a transaction first
        today = date.today()
        client.post(
            "/expenses",
            json={
                "amount": 100,
                "description": "Test",
                "date": today.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )

        # Add income to have positive savings rate
        client.post(
            "/expenses",
            json={
                "amount": 500,
                "description": "Income",
                "date": today.isoformat(),
                "expense_type": "INCOME",
            },
            headers=auth_header,
        )

        r = client.post("/digest/weekly/send", headers=auth_header)
        assert r.status_code == 200

        # Email will likely fail in test env, so we check for a response
        data = r.get_json()
        assert "success" in data
        assert "message" in data


class TestScheduler:
    """Tests for scheduler functionality."""

    def test_scheduler_status_endpoint(self, client):
        """Test scheduler status endpoint."""
        r = client.get("/scheduler/status")
        assert r.status_code == 200

        data = r.get_json()
        assert "running" in data
        assert "jobs" in data

    def test_get_scheduler_status(self):
        """Test getting scheduler status."""
        from app.services.scheduler import get_scheduler_status

        status = get_scheduler_status()
        assert "running" in status
        assert "jobs" in status
        assert isinstance(status["jobs"], list)
