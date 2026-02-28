"""Tests for weekly summary service and API."""
from datetime import date, timedelta
import pytest


class TestWeeklySummaryService:
    """Tests for weekly summary service functions."""

    def test_get_week_boundaries(self):
        from app.services.weekly_summary import _get_week_boundaries
        
        # Test a Wednesday
        wednesday = date(2024, 1, 10)  # This is a Wednesday
        monday, sunday = _get_week_boundaries(wednesday)
        
        assert monday == date(2024, 1, 8)   # Monday of that week
        assert sunday == date(2024, 1, 14)  # Sunday of that week
        
        # Test a Monday
        monday_date = date(2024, 1, 8)
        monday, sunday = _get_week_boundaries(monday_date)
        assert monday == date(2024, 1, 8)
        assert sunday == date(2024, 1, 14)
        
        # Test a Sunday
        sunday_date = date(2024, 1, 14)
        monday, sunday = _get_week_boundaries(sunday_date)
        assert monday == date(2024, 1, 8)
        assert sunday == date(2024, 1, 14)

    def test_get_week_totals_no_data(self, app_fixture):
        from app.services.weekly_summary import _get_week_totals
        
        with app_fixture.app_context():
            income, expenses = _get_week_totals(1, date.today(), date.today())
            assert income == 0
            assert expenses == 0

    def test_get_week_totals_with_data(self, app_fixture):
        from app.services.weekly_summary import _get_week_totals
        from app.extensions import db
        from app.models import Expense
        
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        
        with app_fixture.app_context():
            # Create test expenses
            expense1 = Expense(
                user_id=1,
                amount=100.00,
                currency="INR",
                expense_type="EXPENSE",
                notes="Test expense",
                spent_at=monday,
            )
            expense2 = Expense(
                user_id=1,
                amount=50.00,
                currency="INR",
                expense_type="INCOME",
                notes="Test income",
                spent_at=monday + timedelta(days=1),
            )
            db.session.add(expense1)
            db.session.add(expense2)
            db.session.commit()
            
            income, expenses = _get_week_totals(1, monday, monday + timedelta(days=6))
            assert income == 50.00
            assert expenses == 100.00

    def test_get_category_breakdown(self, app_fixture):
        from app.services.weekly_summary import _get_category_breakdown
        from app.extensions import db
        from app.models import Expense, Category
        
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        
        with app_fixture.app_context():
            # Create category
            cat = Category(user_id=1, name="Food")
            db.session.add(cat)
            db.session.flush()
            
            # Create expense
            expense = Expense(
                user_id=1,
                category_id=cat.id,
                amount=100.00,
                currency="INR",
                expense_type="EXPENSE",
                notes="Lunch",
                spent_at=monday,
            )
            db.session.add(expense)
            db.session.commit()
            
            breakdown = _get_category_breakdown(1, monday, monday + timedelta(days=6))
            assert len(breakdown) == 1
            assert breakdown[0]["category_name"] == "Food"
            assert breakdown[0]["amount"] == 100.00
            assert breakdown[0]["percentage"] == 100.0

    def test_generate_insights(self):
        from app.services.weekly_summary import _generate_insights
        
        # Test spending increase insight
        insights = _generate_insights(120, 100, [{"category_name": "Food", "percentage": 50}], -20)
        assert any("increased" in i.lower() for i in insights)
        
        # Test spending decrease insight
        insights = _generate_insights(80, 100, [{"category_name": "Food", "percentage": 50}], -20)
        assert any("decreased" in i.lower() or "Great job" in i for i in insights)
        
        # Test positive net flow
        insights = _generate_insights(100, 100, [{"category_name": "Food", "percentage": 50}], 50)
        assert any("saved" in i.lower() for i in insights)
        
        # Test negative net flow
        insights = _generate_insights(150, 100, [{"category_name": "Food", "percentage": 50}], -50)
        assert any("spent" in i.lower() and "more" in i.lower() for i in insights)

    def test_generate_weekly_summary(self, app_fixture):
        from app.services.weekly_summary import generate_weekly_summary
        from app.extensions import db
        from app.models import Expense
        
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        
        with app_fixture.app_context():
            # Create test expense
            expense = Expense(
                user_id=1,
                amount=100.00,
                currency="INR",
                expense_type="EXPENSE",
                notes="Test",
                spent_at=monday,
            )
            db.session.add(expense)
            db.session.commit()
            
            summary = generate_weekly_summary(1, today)
            
            assert summary["total_spent"] == 100.00
            assert summary["total_income"] == 0.00
            assert summary["net_flow"] == -100.00
            assert "week_start" in summary
            assert "week_end" in summary
            assert "comparison" in summary
            assert "category_breakdown" in summary
            assert "top_expenses" in summary
            assert "insights" in summary


class TestWeeklySummaryAPI:
    """Tests for weekly summary API endpoints."""

    def test_get_weekly_summary_unauthorized(self, client):
        r = client.get("/weekly-summary")
        assert r.status_code == 401

    def test_get_weekly_summary_success(self, client, auth_header):
        r = client.get("/weekly-summary", headers=auth_header)
        assert r.status_code == 200
        
        data = r.get_json()
        assert "week_start" in data
        assert "week_end" in data
        assert "total_spent" in data
        assert "total_income" in data
        assert "net_flow" in data
        assert "comparison" in data
        assert "category_breakdown" in data
        assert "top_expenses" in data
        assert "insights" in data

    def test_get_weekly_summary_with_week_param(self, client, auth_header):
        # Test with specific week
        test_date = "2024-01-15"
        r = client.get(f"/weekly-summary?week_of={test_date}", headers=auth_header)
        assert r.status_code == 200
        
        data = r.get_json()
        assert "week_start" in data

    def test_get_weekly_summary_invalid_week_param(self, client, auth_header):
        r = client.get("/weekly-summary?week_of=invalid-date", headers=auth_header)
        assert r.status_code == 400
        assert "error" in r.get_json()

    def test_get_weekly_summary_with_expenses(self, client, auth_header):
        from datetime import date as dt
        
        # Create an expense first
        today = dt.today()
        expense_data = {
            "amount": 75.50,
            "description": "Grocery shopping",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
            "currency": "INR",
        }
        r = client.post("/expenses", json=expense_data, headers=auth_header)
        assert r.status_code == 201
        
        # Now get weekly summary
        r = client.get("/weekly-summary", headers=auth_header)
        assert r.status_code == 200
        
        data = r.get_json()
        assert data["total_spent"] == 75.50
        assert len(data["top_expenses"]) == 1
        assert data["top_expenses"][0]["description"] == "Grocery shopping"
