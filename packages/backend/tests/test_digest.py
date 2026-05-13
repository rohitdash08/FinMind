"""Tests for weekly digest service."""
from datetime import date
from app.extensions import db
from app.models import Expense, Category, User
from app.services.digest import (
    get_week_range,
    generate_weekly_digest,
)


def _create_test_user(app_fixture):
    with app_fixture.app_context():
        user = User(email="digest@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()
        return user.id


def _add_expense(uid, amount, cat_id, spent_at, expense_type="EXPENSE"):
    e = Expense(
        user_id=uid,
        category_id=cat_id,
        amount=amount,
        expense_type=expense_type,
        spent_at=spent_at,
        notes="test",
    )
    db.session.add(e)


def test_get_week_range():
    """Week range starts Monday, ends Sunday."""
    # 2026-05-14 is a Thursday
    monday, sunday = get_week_range(date(2026, 5, 14))
    assert monday == date(2026, 5, 11)
    assert sunday == date(2026, 5, 17)


def test_previous_week_range():
    """Previous week is 7 days before."""
    prev_m, prev_s = get_week_range(date(2026, 5, 4))
    assert prev_m == date(2026, 5, 4)
    assert prev_s == date(2026, 5, 10)


def test_generate_digest_empty(app_fixture):
    """Digest with no expenses returns zeros."""
    uid = _create_test_user(app_fixture)
    with app_fixture.app_context():
        digest = generate_weekly_digest(uid, date(2026, 5, 14))
        assert digest["summary"]["total_spent"] == 0
        assert digest["summary"]["total_income"] == 0
        assert digest["summary"]["transaction_count"] == 0
        assert digest["comparison"]["previous_week_spent"] == 0


def test_generate_digest_with_data(app_fixture):
    """Digest correctly aggregates weekly expenses."""
    uid = _create_test_user(app_fixture)
    with app_fixture.app_context():
        cat = Category(user_id=uid, name="Food")
        db.session.add(cat)
        db.session.commit()

        # This week: Monday = 2026-05-11
        _add_expense(uid, 50, cat.id, date(2026, 5, 11))  # Monday
        _add_expense(uid, 30, cat.id, date(2026, 5, 13))  # Wednesday
        _add_expense(uid, 100, cat.id, date(2026, 5, 4))  # LAST week
        _add_expense(uid, 200, cat.id, date(2026, 5, 14), "INCOME")
        db.session.commit()

    with app_fixture.app_context():
        digest = generate_weekly_digest(uid, date(2026, 5, 14))
        assert digest["summary"]["total_spent"] == 80.0  # 50 + 30
        assert digest["summary"]["total_income"] == 200.0
        assert digest["summary"]["transaction_count"] == 3
        assert "Food" in digest["summary"]["category_breakdown"]
        # Comparison with last week
        assert digest["comparison"]["previous_week_spent"] == 100.0
        assert digest["comparison"]["change"] == -20.0  # 80 - 100


def test_digest_without_prev_week(app_fixture):
    """No previous week data returns null comparison."""
    uid = _create_test_user(app_fixture)
    with app_fixture.app_context():
        digest = generate_weekly_digest(uid, date(2026, 5, 14))
        assert digest["comparison"]["change"] is None
        assert digest["comparison"]["change_pct"] is None
