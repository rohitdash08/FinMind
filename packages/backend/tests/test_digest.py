from datetime import date, timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models import User


@pytest.fixture(autouse=True)
def _disable_expense_cache(monkeypatch):
    monkeypatch.setattr(
        "app.routes.expenses.cache_delete_patterns",
        lambda *_args, **_kwargs: None,
    )


def _register_and_auth_header(client, app_fixture, email: str):
    r = client.post("/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code in (201, 409)
    with app_fixture.app_context():
        user = db.session.query(User).filter_by(email=email).first()
        assert user is not None
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _create_expense(client, auth, amount: float, day: date, expense_type="EXPENSE"):
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": f"{expense_type.lower()}-{day.isoformat()}",
            "date": day.isoformat(),
            "expense_type": expense_type,
        },
        headers=auth,
    )
    assert r.status_code == 201


def test_weekly_digest_returns_summary_and_trend_fields(client, app_fixture):
    auth = _register_and_auth_header(client, app_fixture, "digest-user@example.com")
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    iso_year, iso_week, _ = monday.isocalendar()

    _create_expense(client, auth, 1200.0, monday, expense_type="INCOME")
    _create_expense(client, auth, 180.0, monday + timedelta(days=2))

    r = client.get(
        f"/insights/weekly-digest?year={iso_year}&week={iso_week}",
        headers=auth,
    )
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["week"] == f"{iso_year}-W{iso_week:02d}"
    assert set(payload["period"].keys()) == {"start", "end"}
    assert set(payload["totals"].keys()) == {"income", "expenses", "net"}
    assert payload["totals"]["income"] == 1200.0
    assert payload["totals"]["expenses"] == 180.0
    assert payload["totals"]["net"] == 1020.0
    assert payload["transaction_count"] == 2
    assert isinstance(payload["category_breakdown"], list)
    assert isinstance(payload["daily_breakdown"], list)
    assert isinstance(payload["insights"], list)
    assert payload["method"] == "heuristic"


def test_weekly_digest_computes_week_over_week_change(client, app_fixture):
    auth = _register_and_auth_header(client, app_fixture, "digest-wow@example.com")
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    prev_monday = monday - timedelta(days=7)
    iso_year, iso_week, _ = monday.isocalendar()

    _create_expense(client, auth, 200.0, prev_monday)
    _create_expense(client, auth, 100.0, monday)

    r = client.get(
        f"/insights/weekly-digest?year={iso_year}&week={iso_week}",
        headers=auth,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["previous_week_expenses"] == 200.0
    assert payload["week_over_week_change_pct"] == -50.0


def test_weekly_digest_defaults_to_current_week(client, app_fixture):
    auth = _register_and_auth_header(client, app_fixture, "digest-default@example.com")
    r = client.get("/insights/weekly-digest", headers=auth)
    assert r.status_code == 200
    payload = r.get_json()
    year, week, _ = date.today().isocalendar()
    assert payload["week"] == f"{year}-W{week:02d}"


def test_weekly_digest_fallback_when_gemini_errors(client, app_fixture, monkeypatch):
    auth = _register_and_auth_header(client, app_fixture, "digest-ai@example.com")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("gemini down")

    monkeypatch.setattr("app.services.digest._gemini_weekly_insights", _boom)

    r = client.get(
        "/insights/weekly-digest",
        headers={**auth, "X-Gemini-Api-Key": "fake-key"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "heuristic"
    assert "gemini_unavailable" in payload.get("warnings", [])
