"""Tests for database indexes (issue #128).

Verifies that composite indexes are created correctly and that the
queries they are designed to accelerate continue to return correct results.
"""
from datetime import date, timedelta

from app.extensions import db
from app.models import (
    BackgroundJob,
    Bill,
    Category,
    Expense,
    RecurringExpense,
    Reminder,
    User,
)


# ---------------------------------------------------------------------------
# Index existence tests (SQLite PRAGMA)
# ---------------------------------------------------------------------------

def _get_index_names(app_fixture):
    """Return the set of index names present on the test database."""
    with app_fixture.app_context():
        engine = db.engine
        result = engine.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ) if hasattr(engine, "execute") else None

        # Use raw_connection for compatibility
        conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
            return {row[0] for row in cur.fetchall()}
        finally:
            conn.close()


def test_expense_indexes_exist(app_fixture):
    names = _get_index_names(app_fixture)
    assert "ix_expenses_user_spent_at" in names
    assert "ix_expenses_user_category" in names
    assert "ix_expenses_user_type_spent" in names


def test_bill_indexes_exist(app_fixture):
    names = _get_index_names(app_fixture)
    assert "ix_bills_user_due" in names
    assert "ix_bills_user_active" in names


def test_reminder_indexes_exist(app_fixture):
    names = _get_index_names(app_fixture)
    assert "ix_reminders_user_send_at" in names
    assert "ix_reminders_pending" in names


def test_category_index_exists(app_fixture):
    names = _get_index_names(app_fixture)
    assert "ix_categories_user" in names


def test_recurring_expense_index_exists(app_fixture):
    names = _get_index_names(app_fixture)
    assert "ix_recurring_user_active" in names


def test_background_job_indexes_exist(app_fixture):
    names = _get_index_names(app_fixture)
    assert "ix_bg_jobs_status_retry" in names
    assert "ix_bg_jobs_type" in names


# ---------------------------------------------------------------------------
# Query-correctness tests
# ---------------------------------------------------------------------------

def _seed_user(app_fixture):
    """Create a test user directly and return its id."""
    with app_fixture.app_context():
        user = User(
            email="index_test@example.com",
            password_hash="hashed",
            preferred_currency="INR",
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def test_list_expenses_with_date_range(client, auth_header):
    """Expenses filtered by from/to dates should return correct results."""
    # Seed via API to go through normal flow
    for amt, dt in [(10, "2026-01-15"), (20, "2026-02-10"), (30, "2026-03-05")]:
        r = client.post(
            "/expenses",
            json={"amount": amt, "description": f"Item {amt}", "date": dt},
            headers=auth_header,
        )
        assert r.status_code == 201

    # Filter for February only
    r = client.get("/expenses?from=2026-02-01&to=2026-02-28", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["amount"] == 20


def test_list_expenses_with_category_filter(client, auth_header):
    """Expenses filtered by category_id should return correct results."""
    # Create category
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    cat_id = r.get_json()["id"]

    # Create expenses: one with category, one without
    client.post(
        "/expenses",
        json={"amount": 50, "description": "Lunch", "category_id": cat_id, "date": "2026-04-01"},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 100, "description": "Other", "date": "2026-04-01"},
        headers=auth_header,
    )

    r = client.get(f"/expenses?category_id={cat_id}", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["amount"] == 50


def test_dashboard_summary_with_expense_type(client, auth_header):
    """Dashboard query exercises user_id + expense_type + spent_at index."""
    today = date.today().isoformat()
    client.post(
        "/expenses",
        json={"amount": 5000, "description": "Salary", "date": today, "expense_type": "INCOME"},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 200, "description": "Coffee", "date": today, "expense_type": "EXPENSE"},
        headers=auth_header,
    )

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.status_code == 200
    summary = r.get_json()["summary"]
    assert summary["monthly_income"] >= 5000
    assert summary["monthly_expenses"] >= 200


def test_bills_upcoming_query(client, auth_header):
    """Bills filtered by next_due_date exercises ix_bills_user_due."""
    today = date.today()
    client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "next_due_date": (today + timedelta(days=5)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    client.post(
        "/bills",
        json={
            "name": "Old Bill",
            "amount": 10,
            "next_due_date": (today - timedelta(days=30)).isoformat(),
            "cadence": "MONTHLY",
            "active": False,
        },
        headers=auth_header,
    )

    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    bills = r.get_json()
    assert any(b["name"] == "Internet" for b in bills)
