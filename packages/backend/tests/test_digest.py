"""
Tests for weekly digest functionality.
"""
import pytest
from datetime import date, timedelta
from app.models import Expense, Bill, Category, BillCadence


def test_weekly_digest_current_week(client, auth_headers, db_session):
    """Test getting digest for current week."""
    # Get current week
    today = date.today()
    iso_cal = today.isocalendar()
    current_week = f"{iso_cal[0]}-W{iso_cal[1]:02d}"
    
    resp = client.get(
        "/digest/weekly",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json
    
    assert "period" in data
    assert data["period"]["week"] == current_week
    assert "start_date" in data["period"]
    assert "end_date" in data["period"]
    
    assert "expenses" in data
    assert "bills" in data
    assert "comparison" in data
    assert "insights" in data
    assert "generated_at" in data
    assert "insight_method" in data


def test_weekly_digest_specific_week(client, auth_headers, db_session, test_user):
    """Test getting digest for a specific week with data."""
    # Create test data for week 2026-W08 (Feb 16-22, 2026)
    category = Category(user_id=test_user.id, name="Food")
    db_session.add(category)
    db_session.commit()
    
    # Add expenses in the target week
    expenses = [
        Expense(
            user_id=test_user.id,
            category_id=category.id,
            amount=50.00,
            expense_type="EXPENSE",
            notes="Groceries",
            spent_at=date(2026, 2, 17),
        ),
        Expense(
            user_id=test_user.id,
            category_id=category.id,
            amount=30.00,
            expense_type="EXPENSE",
            notes="Restaurant",
            spent_at=date(2026, 2, 19),
        ),
        Expense(
            user_id=test_user.id,
            amount=1000.00,
            expense_type="INCOME",
            notes="Salary",
            spent_at=date(2026, 2, 20),
        ),
    ]
    for exp in expenses:
        db_session.add(exp)
    
    # Add a bill due in the target week
    bill = Bill(
        user_id=test_user.id,
        name="Internet Bill",
        amount=60.00,
        next_due_date=date(2026, 2, 18),
        cadence=BillCadence.MONTHLY,
    )
    db_session.add(bill)
    db_session.commit()
    
    resp = client.get(
        "/digest/weekly?week=2026-W08",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json
    
    # Verify period
    assert data["period"]["week"] == "2026-W08"
    assert data["period"]["start_date"] == "2026-02-16"
    assert data["period"]["end_date"] == "2026-02-22"
    
    # Verify expenses
    assert data["expenses"]["total_income"] == 1000.00
    assert data["expenses"]["total_expenses"] == 80.00
    assert data["expenses"]["net_flow"] == 920.00
    assert len(data["expenses"]["categories"]) == 1
    assert data["expenses"]["categories"][0]["category_name"] == "Food"
    assert data["expenses"]["categories"][0]["amount"] == 80.00
    assert data["expenses"]["categories"][0]["transaction_count"] == 2
    
    # Verify bills
    assert data["bills"]["count"] == 1
    assert data["bills"]["total_amount"] == 60.00
    assert len(data["bills"]["bills"]) == 1
    assert data["bills"]["bills"][0]["name"] == "Internet Bill"
    
    # Verify insights exist
    assert isinstance(data["insights"], list)
    assert len(data["insights"]) > 0


def test_weekly_digest_invalid_week_format(client, auth_headers):
    """Test digest with invalid week format."""
    invalid_weeks = [
        "2026-08",  # Missing W
        "2026W08",  # Missing dash
        "26-W08",   # Year too short
        "2026-W00",  # Week 0
        "2026-W54",  # Week 54
        "invalid",
    ]
    
    for week in invalid_weeks:
        resp = client.get(
            f"/digest/weekly?week={week}",
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "error" in resp.json


def test_weekly_digest_comparison(client, auth_headers, db_session, test_user):
    """Test week-over-week comparison."""
    # Add expenses for two consecutive weeks
    # Week 1: Feb 9-15, 2026 (2026-W07)
    week1_expenses = [
        Expense(
            user_id=test_user.id,
            amount=100.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 10),
        ),
        Expense(
            user_id=test_user.id,
            amount=150.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 12),
        ),
    ]
    
    # Week 2: Feb 16-22, 2026 (2026-W08)
    week2_expenses = [
        Expense(
            user_id=test_user.id,
            amount=200.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 17),
        ),
        Expense(
            user_id=test_user.id,
            amount=100.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 19),
        ),
    ]
    
    for exp in week1_expenses + week2_expenses:
        db_session.add(exp)
    db_session.commit()
    
    resp = client.get(
        "/digest/weekly?week=2026-W08",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json
    
    # Verify comparison
    assert data["comparison"]["current_week_expenses"] == 300.00
    assert data["comparison"]["previous_week_expenses"] == 250.00
    assert data["comparison"]["change_amount"] == 50.00
    assert data["comparison"]["change_percentage"] == 20.00


def test_weekly_digest_daily_spending_pattern(client, auth_headers, db_session, test_user):
    """Test daily spending pattern in digest."""
    # Add expenses across multiple days
    expenses = [
        Expense(
            user_id=test_user.id,
            amount=50.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 16),
        ),
        Expense(
            user_id=test_user.id,
            amount=75.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 17),
        ),
        Expense(
            user_id=test_user.id,
            amount=100.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 18),
        ),
    ]
    
    for exp in expenses:
        db_session.add(exp)
    db_session.commit()
    
    resp = client.get(
        "/digest/weekly?week=2026-W08",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json
    
    # Verify daily spending
    daily = data["expenses"]["daily_spending"]
    assert len(daily) == 3
    assert daily[0]["date"] == "2026-02-16"
    assert daily[0]["amount"] == 50.00
    assert daily[1]["date"] == "2026-02-17"
    assert daily[1]["amount"] == 75.00
    assert daily[2]["date"] == "2026-02-18"
    assert daily[2]["amount"] == 100.00


def test_weekly_digest_multiple_categories(client, auth_headers, db_session, test_user):
    """Test digest with multiple spending categories."""
    # Create categories
    food = Category(user_id=test_user.id, name="Food")
    transport = Category(user_id=test_user.id, name="Transport")
    entertainment = Category(user_id=test_user.id, name="Entertainment")
    db_session.add_all([food, transport, entertainment])
    db_session.commit()
    
    # Add expenses in different categories
    expenses = [
        Expense(
            user_id=test_user.id,
            category_id=food.id,
            amount=200.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 17),
        ),
        Expense(
            user_id=test_user.id,
            category_id=transport.id,
            amount=50.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 18),
        ),
        Expense(
            user_id=test_user.id,
            category_id=entertainment.id,
            amount=100.00,
            expense_type="EXPENSE",
            spent_at=date(2026, 2, 19),
        ),
    ]
    
    for exp in expenses:
        db_session.add(exp)
    db_session.commit()
    
    resp = client.get(
        "/digest/weekly?week=2026-W08",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json
    
    # Verify categories are sorted by amount (descending)
    categories = data["expenses"]["categories"]
    assert len(categories) == 3
    assert categories[0]["category_name"] == "Food"
    assert categories[0]["amount"] == 200.00
    assert categories[1]["category_name"] == "Entertainment"
    assert categories[1]["amount"] == 100.00
    assert categories[2]["category_name"] == "Transport"
    assert categories[2]["amount"] == 50.00


def test_weekly_digest_no_data(client, auth_headers, db_session):
    """Test digest for a week with no data."""
    resp = client.get(
        "/digest/weekly?week=2026-W08",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json
    
    # Should return empty/zero values
    assert data["expenses"]["total_income"] == 0.0
    assert data["expenses"]["total_expenses"] == 0.0
    assert data["expenses"]["net_flow"] == 0.0
    assert len(data["expenses"]["categories"]) == 0
    assert data["bills"]["count"] == 0
    assert data["bills"]["total_amount"] == 0.0


def test_weekly_digest_caching(client, auth_headers, db_session, test_user):
    """Test that digest results are cached."""
    # Add some data
    expense = Expense(
        user_id=test_user.id,
        amount=100.00,
        expense_type="EXPENSE",
        spent_at=date(2026, 2, 17),
    )
    db_session.add(expense)
    db_session.commit()
    
    # First request
    resp1 = client.get(
        "/digest/weekly?week=2026-W08",
        headers=auth_headers,
    )
    assert resp1.status_code == 200
    data1 = resp1.json
    
    # Add more data
    expense2 = Expense(
        user_id=test_user.id,
        amount=50.00,
        expense_type="EXPENSE",
        spent_at=date(2026, 2, 18),
    )
    db_session.add(expense2)
    db_session.commit()
    
    # Second request should return cached data (not including new expense)
    resp2 = client.get(
        "/digest/weekly?week=2026-W08",
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json
    
    # Should be the same (cached)
    assert data1["expenses"]["total_expenses"] == data2["expenses"]["total_expenses"]
    assert data1["generated_at"] == data2["generated_at"]


def test_weekly_digest_unauthorized(client):
    """Test digest endpoint requires authentication."""
    resp = client.get("/digest/weekly")
    assert resp.status_code == 401
