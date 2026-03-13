import pytest
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helper: create an expense via the REST API
# ---------------------------------------------------------------------------


def _post_expense(client, headers, amount, spent_at: date, expense_type="EXPENSE", notes=""):
    return client.post(
        "/expenses",
        json={
            "amount": amount,
            "notes": notes or f"{expense_type} on {spent_at}",
            "date": spent_at.isoformat(),
            "expense_type": expense_type,
        },
        headers=headers,
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


# ---------------------------------------------------------------------------
# Weekly Digest tests
# ---------------------------------------------------------------------------


def _iso_week(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ── 1. Unauthenticated request is rejected ───────────────────────────────────
def test_weekly_digest_requires_auth(client):
    r = client.get("/insights/weekly-digest")
    assert r.status_code == 401


# ── 2. Empty week returns zero totals and valid shape ────────────────────────
def test_weekly_digest_empty_week(client, auth_header):
    # Use a far-past week where no expenses exist
    r = client.get("/insights/weekly-digest?week=2000-W01", headers=auth_header)
    assert r.status_code == 200
    p = r.get_json()

    # Required top-level keys
    for key in (
        "week",
        "period",
        "total_spent",
        "total_income",
        "net_flow",
        "week_over_week_change_pct",
        "previous_week_spent",
        "category_breakdown",
        "daily_breakdown",
        "top_expenses",
        "insights",
        "transaction_count",
    ):
        assert key in p, f"Missing key: {key}"

    assert p["week"] == "2000-W01"
    assert p["total_spent"] == 0.0
    assert p["total_income"] == 0.0
    assert p["net_flow"] == 0.0
    assert p["week_over_week_change_pct"] == 0.0
    assert p["category_breakdown"] == []
    assert len(p["daily_breakdown"]) == 7  # one entry per day
    assert p["top_expenses"] == []
    assert isinstance(p["insights"], list)


# ── 3. Correct aggregation for a populated week ──────────────────────────────
def test_weekly_digest_with_expenses(client, auth_header):
    # Use a specific past week so data is predictable
    target_week = "2024-W10"
    monday = date.fromisocalendar(2024, 10, 1)  # 2024-03-04

    # Create three expenses in that week
    for i, (amt, notes) in enumerate(
        [(100.0, "Groceries"), (50.0, "Transport"), (200.0, "Rent")]
    ):
        r = _post_expense(
            client, auth_header, amt, monday + timedelta(days=i), notes=notes
        )
        assert r.status_code == 201, r.get_json()

    r = client.get(f"/insights/weekly-digest?week={target_week}", headers=auth_header)
    assert r.status_code == 200
    p = r.get_json()

    assert p["week"] == target_week
    assert p["total_spent"] == pytest.approx(350.0)
    assert p["transaction_count"] == 3
    assert len(p["daily_breakdown"]) == 7
    assert len(p["category_breakdown"]) >= 1  # uncategorised bucket
    assert len(p["top_expenses"]) <= 5
    # Top expense should be the largest
    if p["top_expenses"]:
        assert p["top_expenses"][0]["amount"] == pytest.approx(200.0)


# ── 4. Default week (no ?week= param) uses current calendar week ─────────────
def test_weekly_digest_default_week(client, auth_header):
    r = client.get("/insights/weekly-digest", headers=auth_header)
    assert r.status_code == 200
    p = r.get_json()
    expected_week = _iso_week(date.today())
    assert p["week"] == expected_week
    assert "period" in p
    assert "start" in p["period"]
    assert "end" in p["period"]


# ── 5. Week-over-week change is computed correctly ───────────────────────────
def test_weekly_digest_wow_change(client, auth_header):
    # Week A: spend 100, Week B (following week): spend 200 → WoW = +100%
    week_a_monday = date.fromisocalendar(2024, 20, 1)
    week_b_monday = week_a_monday + timedelta(days=7)

    r = _post_expense(client, auth_header, 100.0, week_a_monday, notes="Week A base")
    assert r.status_code == 201
    r = _post_expense(client, auth_header, 200.0, week_b_monday, notes="Week B spend")
    assert r.status_code == 201

    r = client.get(
        f"/insights/weekly-digest?week={_iso_week(week_b_monday)}",
        headers=auth_header,
    )
    assert r.status_code == 200
    p = r.get_json()
    assert p["total_spent"] == pytest.approx(200.0)
    assert p["previous_week_spent"] == pytest.approx(100.0)
    assert p["week_over_week_change_pct"] == pytest.approx(100.0)


# ── 6. Invalid week format returns 400 ───────────────────────────────────────
def test_weekly_digest_invalid_week_format(client, auth_header):
    r = client.get("/insights/weekly-digest?week=not-a-week", headers=auth_header)
    assert r.status_code == 400
    p = r.get_json()
    assert p["error"] == "invalid_week_format"


# ── 7. Income is tracked and net_flow is correct ─────────────────────────────
def test_weekly_digest_income_and_net_flow(client, auth_header):
    week = "2024-W30"
    monday = date.fromisocalendar(2024, 30, 1)

    r = _post_expense(
        client, auth_header, 500.0, monday, expense_type="INCOME", notes="Salary"
    )
    assert r.status_code == 201
    r = _post_expense(
        client, auth_header, 200.0, monday + timedelta(days=1), notes="Rent"
    )
    assert r.status_code == 201

    r = client.get(f"/insights/weekly-digest?week={week}", headers=auth_header)
    assert r.status_code == 200
    p = r.get_json()
    assert p["total_income"] == pytest.approx(500.0)
    assert p["total_spent"] == pytest.approx(200.0)
    assert p["net_flow"] == pytest.approx(300.0)


# ── 8. Period dates match ISO week boundaries ─────────────────────────────────
def test_weekly_digest_period_dates(client, auth_header):
    r = client.get("/insights/weekly-digest?week=2024-W10", headers=auth_header)
    assert r.status_code == 200
    p = r.get_json()
    assert p["period"]["start"] == "2024-03-04"  # Monday of W10 2024
    assert p["period"]["end"] == "2024-03-10"    # Sunday of W10 2024
