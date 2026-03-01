"""Tests for the weekly financial digest feature."""

from datetime import date, timedelta


def _seed_expenses(client, auth_header, dates_amounts):
    """Helper: create expenses on given (date, amount) pairs."""
    for d, amt in dates_amounts:
        r = client.post(
            "/expenses",
            json={
                "amount": amt,
                "description": f"Expense {amt}",
                "date": d.isoformat(),
                "expense_type": "EXPENSE",
            },
            headers=auth_header,
        )
        assert r.status_code == 201


def _seed_income(client, auth_header, d, amt):
    r = client.post(
        "/expenses",
        json={
            "amount": amt,
            "description": "Income",
            "date": d.isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    assert r.status_code == 201


# ── GET /digest/weekly ─────────────────────────────────────────────────────


def test_weekly_digest_empty(client, auth_header):
    """Digest should return valid structure even with no data."""
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "period" in data
    assert "summary" in data
    assert "trends" in data
    assert "category_breakdown" in data
    assert "upcoming_bills" in data
    assert data["summary"]["total_expenses"] == 0.0
    assert data["summary"]["total_income"] == 0.0


def test_weekly_digest_with_expenses(client, auth_header):
    """Digest picks up expenses from the correct week."""
    # Use a known ref_date so we control which week
    ref = date(2025, 3, 5)  # Wednesday → last full week is Feb 24–Mar 2
    week_start = date(2025, 2, 24)

    _seed_expenses(client, auth_header, [
        (week_start, 100),
        (week_start + timedelta(days=2), 50),
    ])

    r = client.get(
        f"/digest/weekly?ref_date={ref.isoformat()}",
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["total_expenses"] == 150.0
    assert data["period"]["start"] == "2025-02-24"
    assert data["period"]["end"] == "2025-03-02"


def test_weekly_digest_trends(client, auth_header):
    """Trends should compare current vs previous week."""
    ref = date(2025, 3, 5)
    cur_week_start = date(2025, 2, 24)
    prev_week_start = date(2025, 2, 17)

    _seed_expenses(client, auth_header, [
        (prev_week_start, 100),
        (cur_week_start, 200),
    ])

    r = client.get(
        f"/digest/weekly?ref_date={ref.isoformat()}",
        headers=auth_header,
    )
    data = r.get_json()
    assert data["trends"]["direction"] == "up"
    assert data["trends"]["spending_change_pct"] == 100.0


def test_weekly_digest_income_and_net_flow(client, auth_header):
    ref = date(2025, 3, 5)
    week_start = date(2025, 2, 24)

    _seed_expenses(client, auth_header, [(week_start, 300)])
    _seed_income(client, auth_header, week_start, 1000)

    r = client.get(
        f"/digest/weekly?ref_date={ref.isoformat()}",
        headers=auth_header,
    )
    data = r.get_json()
    assert data["summary"]["total_income"] == 1000.0
    assert data["summary"]["net_flow"] == 700.0


# ── POST /digest/weekly/send ──────────────────────────────────────────────


def test_send_digest_endpoint(client, auth_header, monkeypatch):
    """Send endpoint should call delivery and return results."""
    sent = []

    def _fake_email(to, subject, body):
        sent.append(("email", to, subject))
        return True

    monkeypatch.setattr("app.services.reminders.send_email", _fake_email)
    # Also patch in the route module's import
    monkeypatch.setattr("app.routes.digest.send_email", _fake_email)

    r = client.post(
        "/digest/weekly/send",
        json={"email": True},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "digest" in data
    assert data["delivery"]["email"] == "sent"
    assert len(sent) >= 1


def test_send_digest_whatsapp(client, auth_header, monkeypatch):
    sent = []

    def _fake_email(*a, **kw):
        return False

    def _fake_whatsapp(to, body):
        sent.append(("whatsapp", to))
        return True

    monkeypatch.setattr("app.routes.digest.send_email", _fake_email)
    monkeypatch.setattr("app.routes.digest.send_whatsapp", _fake_whatsapp)

    r = client.post(
        "/digest/weekly/send",
        json={"email": False, "whatsapp": "whatsapp:+1234567890"},
        headers=auth_header,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["delivery"]["whatsapp"] == "sent"


# ── Digest text formatting ───────────────────────────────────────────────


def test_format_digest_text():
    from app.services.digest import format_digest_text

    digest = {
        "period": {"start": "2025-02-24", "end": "2025-03-02"},
        "summary": {"total_income": 1000.0, "total_expenses": 500.0, "net_flow": 500.0},
        "category_breakdown": [
            {"category_id": 1, "category_name": "Food", "total": 300.0},
            {"category_id": 2, "category_name": "Transport", "total": 200.0},
        ],
        "trends": {
            "spending_change_pct": -10.0,
            "direction": "down",
            "current_week_total": 500.0,
            "previous_week_total": 555.56,
        },
        "upcoming_bills": [
            {"name": "Netflix", "amount": 15.99, "next_due_date": "2025-03-05"},
        ],
        "upcoming_bills_total": 15.99,
        "generated_at": "2025-03-03",
    }

    text = format_digest_text(digest)
    assert "Weekly Digest" in text
    assert "Food" in text
    assert "Netflix" in text
    assert "-10.0%" in text


# ── Scheduler registration ───────────────────────────────────────────────


def test_scheduler_module_importable():
    """Ensure scheduler module loads without errors."""
    from app.scheduler import init_scheduler  # noqa: F401
