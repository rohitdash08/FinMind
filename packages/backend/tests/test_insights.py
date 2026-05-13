from datetime import date, timedelta

from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models import Category, Expense, User


def test_budget_suggestion_returns_analytics_fields(client, auth_header):
    current = date.today().replace(day=10)
    previous = (current.replace(day=1) - timedelta(days=1)).replace(day=10)

    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Current month spend",
            "date": current.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Previous month spend",
            "date": previous.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    ym = current.strftime("%Y-%m")
    r = client.get(f"/insights/budget-suggestion?month={ym}", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "analytics" in payload
    assert "month_over_month_change_pct" in payload["analytics"]
    assert payload["month"] == ym


def test_budget_suggestion_prefers_user_gemini_key(client, auth_header, monkeypatch):
    captured = {}

    def _fake_gemini(uid, ym, api_key, model, persona):
        captured["uid"] = uid
        captured["ym"] = ym
        captured["api_key"] = api_key
        captured["model"] = model
        captured["persona"] = persona
        return {
            "suggested_total": 777.0,
            "breakdown": {"needs": 300, "wants": 200, "savings": 277},
            "tips": ["Tip 1", "Tip 2"],
            "method": "gemini",
        }

    monkeypatch.setattr("app.services.ai._gemini_budget_suggestion", _fake_gemini)

    r = client.get(
        "/insights/budget-suggestion",
        headers={
            **auth_header,
            "X-Gemini-Api-Key": "user-supplied-key",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "gemini"
    assert payload["suggested_total"] == 777.0
    assert captured["api_key"] == "user-supplied-key"


def test_budget_suggestion_falls_back_when_gemini_fails(
    client, auth_header, monkeypatch
):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.ai._gemini_budget_suggestion", _boom)

    r = client.get(
        "/insights/budget-suggestion",
        headers={
            **auth_header,
            "X-Gemini-Api-Key": "user-supplied-key",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "heuristic"
    assert "warnings" in payload
    assert "gemini_unavailable" in payload["warnings"]


def _auth_header_without_redis(app_fixture):
    with app_fixture.app_context():
        user = User(email="digest@example.com", password_hash="unused")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    return user.id, {"Authorization": f"Bearer {token}"}


def test_weekly_digest_returns_summary_trends_and_actions(client, app_fixture):
    uid, auth_header = _auth_header_without_redis(app_fixture)
    week_start = date(2026, 5, 11)
    previous_week = week_start - timedelta(days=7)
    with app_fixture.app_context():
        groceries = Category(user_id=uid, name="Groceries")
        db.session.add(groceries)
        db.session.flush()
        db.session.add_all(
            [
                Expense(
                    user_id=uid,
                    category_id=groceries.id,
                    amount=100,
                    expense_type="EXPENSE",
                    notes="Groceries",
                    spent_at=week_start,
                ),
                Expense(
                    user_id=uid,
                    amount=50,
                    expense_type="EXPENSE",
                    notes="Transport",
                    spent_at=week_start + timedelta(days=1),
                ),
                Expense(
                    user_id=uid,
                    amount=300,
                    expense_type="INCOME",
                    notes="Freelance",
                    spent_at=week_start + timedelta(days=2),
                ),
                Expense(
                    user_id=uid,
                    amount=100,
                    expense_type="EXPENSE",
                    notes="Prior week",
                    spent_at=previous_week,
                ),
            ]
        )
        db.session.commit()

    r = client.get(
        f"/insights/weekly-digest?week_start={week_start.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["period"]["week_start"] == week_start.isoformat()
    assert payload["summary"]["income"] == 300.0
    assert payload["summary"]["expenses"] == 150.0
    assert payload["summary"]["net_flow"] == 150.0
    assert payload["summary"]["previous_week_expenses"] == 100.0
    assert payload["summary"]["spending_change_pct"] == 50.0
    assert payload["top_categories"][0]["category_name"] == "Groceries"
    assert payload["insights"]
    assert payload["recommended_actions"]


def test_weekly_digest_rejects_invalid_week_start(client, app_fixture):
    _, auth_header = _auth_header_without_redis(app_fixture)

    r = client.get("/insights/weekly-digest?week_start=not-a-date", headers=auth_header)
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid week_start, expected YYYY-MM-DD"
