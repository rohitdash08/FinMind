from datetime import date, timedelta

import pytest
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User


@pytest.fixture()
def auth_header(app_fixture):
    with app_fixture.app_context():
        user = User(
            email="insights-test@example.com",
            password_hash=generate_password_hash("password123"),
            preferred_currency="INR",
        )
        db.session.add(user)
        db.session.commit()
        access = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {access}"}


@pytest.fixture(autouse=True)
def disable_cache_invalidation(monkeypatch):
    monkeypatch.setattr(
        "app.routes.expenses.cache_delete_patterns",
        lambda _patterns: None,
    )
    monkeypatch.setattr(
        "app.routes.bills.cache_delete_patterns",
        lambda _patterns: None,
    )


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


def test_weekly_summary_returns_trends_categories_and_bills(client, auth_header):
    monday = date.today() - timedelta(days=date.today().weekday())
    previous_monday = monday - timedelta(days=7)

    r = client.post("/categories", json={"name": "Groceries"}, headers=auth_header)
    assert r.status_code == 201
    groceries_id = r.get_json()["id"]

    r = client.post(
        "/expenses",
        json={
            "amount": 1200,
            "description": "Salary",
            "date": monday.isoformat(),
            "expense_type": "INCOME",
            "currency": "USD",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 300,
            "description": "Weekly groceries",
            "date": (monday + timedelta(days=1)).isoformat(),
            "expense_type": "EXPENSE",
            "category_id": groceries_id,
            "currency": "USD",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Previous groceries",
            "date": (previous_monday + timedelta(days=1)).isoformat(),
            "expense_type": "EXPENSE",
            "category_id": groceries_id,
            "currency": "USD",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "currency": "USD",
            "next_due_date": (monday + timedelta(days=4)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(
        f"/insights/weekly-summary?week_start={monday.isoformat()}&currency=USD",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["period"]["week_start"] == monday.isoformat()
    assert payload["currency"] == "USD"
    assert payload["summary"]["income"] == 1200.0
    assert payload["summary"]["expenses"] == 300.0
    assert payload["summary"]["previous_expenses"] == 200.0
    assert payload["summary"]["expense_change_pct"] == 50.0
    assert payload["summary"]["expense_trend"] == "up"
    assert len(payload["daily"]) == 7
    assert payload["category_breakdown"][0]["category_name"] == "Groceries"
    assert payload["category_breakdown"][0]["amount"] == 300.0
    assert payload["upcoming_bills"][0]["name"] == "Internet"
    assert payload["insights"]
    assert payload["recommendations"]


def test_weekly_summary_rejects_invalid_date(client, auth_header):
    r = client.get("/insights/weekly-summary?week_start=bad-date", headers=auth_header)
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid week_start"
