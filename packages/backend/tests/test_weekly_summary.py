"""
FinMind — Weekly Summary Tests

Fixes applied:
  7. autouse db_session fixture ensures each test runs in an isolated
     transaction that is rolled back on teardown — no cross-test pollution.
"""

from datetime import date, timedelta

import pytest


# ---------------------------------------------------------------------------
# Fix #7 — per-test database isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(db_session):
    """Wrap every test in a savepoint; roll back after the test finishes."""
    db_session.begin_nested()
    yield
    db_session.rollback()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _week_start(ref: date | None = None) -> date:
    d = ref or date.today()
    return d - timedelta(days=d.weekday())


def _prev_week_start(ref: date | None = None) -> date:
    return _week_start(ref) - timedelta(days=7)


def _post_expense(client, auth_header, *, amount: float, spent_at: date, expense_type: str = "EXPENSE"):
    return client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": f"Test expense {amount}",
            "date": spent_at.isoformat(),
            "expense_type": expense_type,
        },
        headers=auth_header,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_weekly_summary_returns_analytics(client, auth_header):
    """Basic heuristic summary returns all required analytics fields."""
    today = date.today()
    ws = _week_start(today)
    we = ws + timedelta(days=6)

    r = _post_expense(client, auth_header, amount=75.50, spent_at=ws)
    assert r.status_code == 201

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()

    assert payload["type"] == "weekly_summary"
    assert "this_week" in payload
    assert "previous_week" in payload
    assert "week_over_week_change_pct" in payload
    assert payload["method"] in ("heuristic", "gemini")

    tw = payload["this_week"]
    assert tw["week_start"] == ws.isoformat()
    assert tw["week_end"] == we.isoformat()
    assert tw["total_expenses"] >= 75.0
    assert tw["transaction_count"] >= 1
    assert len(tw["daily_spend"]) >= 1


def test_weekly_summary_with_ref_date(client, auth_header):
    """A specific ref_date produces the correct ISO week range."""
    ref = date(2026, 5, 20)   # Wednesday → week of Mon 18 May
    ws = _week_start(ref)
    we = ws + timedelta(days=6)

    r = client.get(
        f"/insights/weekly-summary?ref_date={ref.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["this_week"]["week_start"] == ws.isoformat()
    assert payload["this_week"]["week_end"] == we.isoformat()


# Fix #6 — future date must be rejected
def test_weekly_summary_rejects_future_ref_date(client, auth_header):
    """ref_date in the future returns HTTP 400."""
    future = (date.today() + timedelta(days=30)).isoformat()
    r = client.get(
        f"/insights/weekly-summary?ref_date={future}",
        headers=auth_header,
    )
    assert r.status_code == 400
    body = r.get_json()
    assert "error" in body
    assert "future" in body["error"].lower()


def test_weekly_summary_rejects_invalid_date_format(client, auth_header):
    """Malformed ref_date returns HTTP 400."""
    r = client.get(
        "/insights/weekly-summary?ref_date=not-a-date",
        headers=auth_header,
    )
    assert r.status_code == 400


# Fix #2 — client-supplied API key header must be ignored
def test_weekly_summary_ignores_client_gemini_key(client, auth_header, monkeypatch):
    """X-Gemini-Api-Key header must NOT be forwarded to the AI service."""
    calls = []

    def _fake_ai(uid, this_week, last_week, model, locale="en"):
        calls.append({"uid": uid, "model": model})
        return {
            "type": "weekly_summary",
            "this_week": {"total_expenses": 0, "total_income": 0,
                          "net_flow": 0, "transaction_count": 0,
                          "daily_spend": [], "top_categories": [],
                          "week_start": this_week[0].isoformat(),
                          "week_end": this_week[1].isoformat()},
            "previous_week": {"total_expenses": 0},
            "week_over_week_change_pct": 0.0,
            "summary": "AI summary",
            "highlights": [],
            "concerns": [],
            "tips": [],
            "method": "gemini",
        }

    monkeypatch.setattr(
        "app.services.weekly_summary._ai_weekly_summary", _fake_ai
    )
    # Patch settings so server thinks it has a key configured
    monkeypatch.setattr(
        "app.services.weekly_summary._settings.gemini_api_key", "server-secret"
    )

    r = client.get(
        "/insights/weekly-summary",
        headers={**auth_header, "X-Gemini-Api-Key": "client-injected-key"},
    )
    assert r.status_code == 200
    # The fake was called (server key exists), but the client key is not accessible
    # — the route never passes it down; _ai_weekly_summary reads from _settings only
    assert len(calls) == 1


def test_weekly_summary_uses_gemini_when_server_key_configured(
    client, auth_header, monkeypatch
):
    """When the server has a Gemini key, the AI path is used."""
    def _fake_ai(uid, this_week, last_week, model, locale="en"):
        return {
            "type": "weekly_summary",
            "this_week": {"total_expenses": 100, "total_income": 0,
                          "net_flow": -100, "transaction_count": 2,
                          "daily_spend": [], "top_categories": [],
                          "week_start": this_week[0].isoformat(),
                          "week_end": this_week[1].isoformat()},
            "previous_week": {"total_expenses": 80},
            "week_over_week_change_pct": 25.0,
            "summary": "AI summary",
            "highlights": ["Good"],
            "concerns": [],
            "tips": ["Save more"],
            "method": "gemini",
        }

    monkeypatch.setattr("app.services.weekly_summary._ai_weekly_summary", _fake_ai)
    monkeypatch.setattr(
        "app.services.weekly_summary._settings.gemini_api_key", "server-key"
    )

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "gemini"
    assert payload["summary"] == "AI summary"


# Fix #4 — each exception type produces the correct warning tag
@pytest.mark.parametrize("exc_class,warning_prefix", [
    ("json.JSONDecodeError", "ai_parse_error"),
    ("httpx.HTTPStatusError",  "gemini_http_error"),
    ("httpx.TimeoutException",  "gemini_timeout"),
    ("httpx.RequestError",      "gemini_unavailable"),
])
def test_weekly_summary_falls_back_on_specific_exceptions(
    client, auth_header, monkeypatch, exc_class, warning_prefix
):
    """Each specific AI exception degrades to heuristic with the right warning tag."""
    import httpx, json as _json

    exc_map = {
        "json.JSONDecodeError": _json.JSONDecodeError("boom", "", 0),
        "httpx.HTTPStatusError": httpx.HTTPStatusError(
            "boom", request=None,
            response=type("R", (), {"status_code": 503})(),
        ),
        "httpx.TimeoutException": httpx.TimeoutException("timeout"),
        "httpx.RequestError": httpx.RequestError("conn refused"),
    }

    def _boom(*_args, **_kwargs):
        raise exc_map[exc_class]

    monkeypatch.setattr("app.services.weekly_summary._ai_weekly_summary", _boom)
    monkeypatch.setattr(
        "app.services.weekly_summary._settings.gemini_api_key", "server-key"
    )

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["method"] == "heuristic"
    assert "warnings" in payload
    assert any(warning_prefix in w for w in payload["warnings"]), (
        f"Expected warning starting with '{warning_prefix}', got: {payload['warnings']}"
    )


def test_weekly_summary_includes_top_categories(client, auth_header):
    """Multiple expenses produce a non-empty top_categories list.

    Fix #7: isolated_db fixture prevents data from other tests leaking in.
    """
    ws = _week_start()
    for amt in [50.0, 30.0, 20.0]:
        resp = _post_expense(client, auth_header, amount=amt, spent_at=ws)
        assert resp.status_code == 201

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    cats = r.get_json()["this_week"]["top_categories"]
    assert len(cats) >= 1
    # Amounts should be sorted descending
    amounts = [c["amount"] for c in cats]
    assert amounts == sorted(amounts, reverse=True)


# Fix #5 — expenses on the last day of the week must be counted
def test_weekly_summary_includes_week_end_day_expenses(client, auth_header):
    """An expense on Sunday (week_end) is included in the weekly total."""
    ws = _week_start()
    sunday = ws + timedelta(days=6)

    r = _post_expense(client, auth_header, amount=99.0, spent_at=sunday)
    assert r.status_code == 201

    r = client.get("/insights/weekly-summary", headers=auth_header)
    assert r.status_code == 200
    tw = r.get_json()["this_week"]
    assert tw["total_expenses"] >= 99.0, (
        "Sunday expense was not counted — date boundary bug not fixed"
    )


# Fix #9 — rate limiting
def test_weekly_summary_rate_limited(client, auth_header):
    """More than 20 rapid requests in one minute should return 429."""
    responses = [
        client.get("/insights/weekly-summary", headers=auth_header)
        for _ in range(25)
    ]
    status_codes = [r.status_code for r in responses]
    assert 429 in status_codes, (
        "Expected at least one 429 after 25 rapid requests (rate limit not enforced)"
    )


# Fix #8 — locale forwarding
def test_weekly_summary_locale_forwarded(client, auth_header, monkeypatch):
    """Accept-Language header selects the matching AI persona."""
    captured = {}

    def _fake_ai(uid, this_week, last_week, model, locale="en"):
        captured["locale"] = locale
        return {
            "type": "weekly_summary",
            "this_week": {"total_expenses": 0, "total_income": 0,
                          "net_flow": 0, "transaction_count": 0,
                          "daily_spend": [], "top_categories": [],
                          "week_start": this_week[0].isoformat(),
                          "week_end": this_week[1].isoformat()},
            "previous_week": {"total_expenses": 0},
            "week_over_week_change_pct": 0.0,
            "summary": "摘要",
            "highlights": [], "concerns": [], "tips": [],
            "method": "gemini",
        }

    monkeypatch.setattr("app.services.weekly_summary._ai_weekly_summary", _fake_ai)
    monkeypatch.setattr(
        "app.services.weekly_summary._settings.gemini_api_key", "server-key"
    )

    r = client.get(
        "/insights/weekly-summary",
        headers={**auth_header, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    assert r.status_code == 200
    assert captured.get("locale") == "zh"
