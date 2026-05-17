from datetime import date, timedelta

from app.extensions import db
from app.models import Category, User


def _week_anchor() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _create_category(app_fixture, auth_header, name="Groceries"):
    with app_fixture.app_context():
        user = db.session.query(User).filter_by(email="test@example.com").one()
        category = Category(user_id=user.id, name=name)
        db.session.add(category)
        db.session.commit()
        return category.id


def test_weekly_digest_returns_summary_trends_and_insights(
    client, app_fixture, auth_header
):
    category_id = _create_category(app_fixture, auth_header)
    week_start = _week_anchor()
    previous_week = week_start - timedelta(days=7)

    expenses = [
        ("Weekly groceries", 120, week_start, "EXPENSE"),
        ("Coffee", 30, week_start + timedelta(days=1), "EXPENSE"),
        ("Salary", 500, week_start + timedelta(days=2), "INCOME"),
        ("Previous groceries", 100, previous_week, "EXPENSE"),
    ]
    for description, amount, spent_at, expense_type in expenses:
        r = client.post(
            "/expenses",
            json={
                "amount": amount,
                "description": description,
                "date": spent_at.isoformat(),
                "expense_type": expense_type,
                "category_id": category_id if expense_type != "INCOME" else None,
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get(
        f"/insights/weekly-digest?week_start={week_start.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["week_start"] == week_start.isoformat()
    assert payload["week_end"] == (week_start + timedelta(days=6)).isoformat()
    assert payload["summary"]["spending"] == 150.0
    assert payload["summary"]["income"] == 500.0
    assert payload["summary"]["net_flow"] == 350.0
    assert payload["summary"]["transaction_count"] == 3
    assert payload["summary"]["top_categories"][0]["category"] == "Groceries"
    assert payload["comparison"]["previous_spending"] == 100.0
    assert payload["comparison"]["spending_change_pct"] == 50.0
    assert any("Spending increased" in insight for insight in payload["insights"])


def test_weekly_digest_rejects_invalid_week_start(client, auth_header):
    r = client.get("/insights/weekly-digest?week_start=nope", headers=auth_header)
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid week_start"
