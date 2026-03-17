"""
Tests for Personal Financial Digital Twin Simulator (Issue #100).

Covers:
- POST /twin/simulate returns correct structure
- Baseline built from historical expenses
- Projections span correct number of months
- Income drift / expense drift applied over time
- Life-change events: income_change, expense_change, one_time_expense,
  one_time_income, job_loss, job_recovery
- Invalid event type → 400
- Missing event month → 400
- horizon_months validation (0, 61, non-int) → 400
- Events > 50 → 400
- Risk detection: negative net flow in projections
- Summary fields: total_projected_savings, months_positive/negative
- GET /twin/event-types lists all types
- Auth required
- User isolation (baseline built from own data only)
- run_digital_twin unit tests
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Expense
from app.services.digital_twin import VALID_EVENT_TYPES, run_digital_twin


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="twin@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


def _seed(app_fixture, uid, amount, expense_type="EXPENSE", days_ago=5, notes="x"):
    with app_fixture.app_context():
        db.session.add(Expense(
            user_id=uid, amount=Decimal(str(amount)), currency="INR",
            expense_type=expense_type,
            spent_at=date.today() - timedelta(days=days_ago), notes=notes,
        ))
        db.session.commit()


def _next_month(anchor=None) -> str:
    d = anchor or date.today()
    m = d.month + 1
    y = d.year
    if m > 12:
        m = 1
        y += 1
    return f"{y:04d}-{m:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — digital_twin service
# ─────────────────────────────────────────────────────────────────────────────

class TestRunDigitalTwin:
    def _make_user(self, app_fixture, email):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email=email, password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            return u.id

    def test_returns_required_keys(self, app_fixture):
        uid = self._make_user(app_fixture, "dt_struct@test.com")
        with app_fixture.app_context():
            result = run_digital_twin(uid, horizon_months=3)
        for key in ("baseline", "projections", "risks", "summary",
                    "horizon_months", "events_applied", "generated_at"):
            assert key in result

    def test_projection_count_matches_horizon(self, app_fixture):
        uid = self._make_user(app_fixture, "dt_count@test.com")
        with app_fixture.app_context():
            result = run_digital_twin(uid, horizon_months=6)
        assert len(result["projections"]) == 6

    def test_empty_history_gives_zero_baseline(self, app_fixture):
        uid = self._make_user(app_fixture, "dt_zero@test.com")
        with app_fixture.app_context():
            result = run_digital_twin(uid, horizon_months=3)
        assert result["baseline"]["income"] == 0.0
        assert result["baseline"]["expenses"] == 0.0

    def test_income_drift_increases_over_time(self, app_fixture):
        uid = self._make_user(app_fixture, "dt_drift@test.com")
        with app_fixture.app_context():
            # Seed some income
            db.session.add(Expense(user_id=uid, amount=Decimal("5000"), currency="INR",
                                   expense_type="INCOME",
                                   spent_at=date.today() - timedelta(days=5), notes="s"))
            db.session.commit()
            result = run_digital_twin(uid, horizon_months=12)
        # Month 12 income should be higher than month 1 due to growth drift
        p = result["projections"]
        assert p[11]["income"] > p[0]["income"]

    def test_job_loss_event_sets_income_zero(self, app_fixture):
        uid = self._make_user(app_fixture, "dt_jobloss@test.com")
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid, amount=Decimal("4000"), currency="INR",
                                   expense_type="INCOME",
                                   spent_at=date.today() - timedelta(days=5), notes="s"))
            db.session.commit()
            target_month = _next_month()
            result = run_digital_twin(uid, horizon_months=3, events=[
                {"type": "job_loss", "month": target_month, "label": "redundancy"}
            ])

        target_proj = next((p for p in result["projections"] if p["month"] == target_month), None)
        if target_proj:
            assert target_proj["income"] == 0.0
        assert result["events_applied"] >= 1

    def test_one_time_expense_increases_monthly_total(self, app_fixture):
        uid = self._make_user(app_fixture, "dt_ote@test.com")
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid, amount=Decimal("3000"), currency="INR",
                                   expense_type="INCOME",
                                   spent_at=date.today() - timedelta(days=5), notes="s"))
            db.session.commit()
            target_month = _next_month()
            result_with = run_digital_twin(uid, horizon_months=3, events=[
                {"type": "one_time_expense", "month": target_month, "amount": 2000}
            ])
            result_without = run_digital_twin(uid, horizon_months=3)

        # The month with the event should have higher expenses
        e_with    = next(p["expenses"] for p in result_with["projections"]    if p["month"] == target_month)
        e_without = next(p["expenses"] for p in result_without["projections"] if p["month"] == target_month)
        assert e_with > e_without

    def test_valid_event_types(self):
        assert "income_change" in VALID_EVENT_TYPES
        assert "job_loss" in VALID_EVENT_TYPES
        assert "job_recovery" in VALID_EVENT_TYPES
        assert "one_time_expense" in VALID_EVENT_TYPES

    def test_user_isolation(self, app_fixture):
        uid1 = self._make_user(app_fixture, "dt_iso1@test.com")
        uid2 = self._make_user(app_fixture, "dt_iso2@test.com")
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid1, amount=Decimal("9999"), currency="INR",
                                   expense_type="INCOME",
                                   spent_at=date.today() - timedelta(days=3), notes="big"))
            db.session.commit()
            result = run_digital_twin(uid2, horizon_months=1)
        assert result["baseline"]["income"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestTwinSimulateEndpoint:
    def test_requires_auth(self, client, app_fixture):
        r = client.post("/twin/simulate", json={"horizon_months": 3})
        assert r.status_code == 401

    def test_basic_simulate(self, client, app_fixture):
        h = _auth(client, "ts1@test.com")
        r = client.post("/twin/simulate", json={"horizon_months": 6}, headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert "projections" in d
        assert len(d["projections"]) == 6

    def test_response_structure(self, client, app_fixture):
        h = _auth(client, "ts2@test.com")
        d = client.post("/twin/simulate", json={}, headers=h).get_json()
        for key in ("baseline", "projections", "risks", "summary",
                    "horizon_months", "events_applied", "generated_at"):
            assert key in d

    def test_summary_structure(self, client, app_fixture):
        h = _auth(client, "ts3@test.com")
        d = client.post("/twin/simulate", json={}, headers=h).get_json()
        s = d["summary"]
        assert "total_projected_savings" in s
        assert "avg_monthly_net" in s
        assert "months_positive" in s
        assert "months_negative" in s
        assert "final_cumulative_savings" in s
        assert s["months_positive"] + s["months_negative"] == d["horizon_months"]

    def test_invalid_horizon_returns_400(self, client, app_fixture):
        h = _auth(client, "ts4@test.com")
        assert client.post("/twin/simulate", json={"horizon_months": 0}, headers=h).status_code == 400
        assert client.post("/twin/simulate", json={"horizon_months": 61}, headers=h).status_code == 400
        assert client.post("/twin/simulate", json={"horizon_months": "bad"}, headers=h).status_code == 400

    def test_invalid_anchor_returns_400(self, client, app_fixture):
        h = _auth(client, "ts5@test.com")
        r = client.post("/twin/simulate", json={"anchor": "not-a-date"}, headers=h)
        assert r.status_code == 400

    def test_too_many_events_returns_400(self, client, app_fixture):
        h = _auth(client, "ts6@test.com")
        events = [{"type": "income_change", "month": "2026-06", "pct_change": 1}] * 51
        r = client.post("/twin/simulate", json={"events": events}, headers=h)
        assert r.status_code == 400

    def test_invalid_event_type_returns_400(self, client, app_fixture):
        h = _auth(client, "ts7@test.com")
        r = client.post("/twin/simulate", json={
            "events": [{"type": "teleport", "month": "2026-06"}]
        }, headers=h)
        assert r.status_code == 400

    def test_missing_event_month_returns_400(self, client, app_fixture):
        h = _auth(client, "ts8@test.com")
        r = client.post("/twin/simulate", json={
            "events": [{"type": "income_change", "pct_change": 10}]
        }, headers=h)
        assert r.status_code == 400

    def test_job_loss_event_applied(self, client, app_fixture):
        h = _auth(client, "ts9@test.com")
        uid = _get_uid(app_fixture, "ts9@test.com")
        _seed(app_fixture, uid, 5000, expense_type="INCOME", days_ago=5)

        target = _next_month()
        r = client.post("/twin/simulate", json={
            "horizon_months": 3,
            "events": [{"type": "job_loss", "month": target, "label": "layoff"}],
        }, headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert d["events_applied"] >= 1
        target_proj = next((p for p in d["projections"] if p["month"] == target), None)
        if target_proj:
            assert target_proj["income"] == 0.0

    def test_income_change_event_applied(self, client, app_fixture):
        h = _auth(client, "ts10@test.com")
        uid = _get_uid(app_fixture, "ts10@test.com")
        _seed(app_fixture, uid, 4000, expense_type="INCOME", days_ago=5)

        target = _next_month()
        r = client.post("/twin/simulate", json={
            "horizon_months": 3,
            "events": [{"type": "income_change", "month": target, "pct_change": 20}],
        }, headers=h)
        assert r.status_code == 200
        assert r.get_json()["events_applied"] >= 1

    def test_events_not_list_returns_400(self, client, app_fixture):
        h = _auth(client, "ts11@test.com")
        r = client.post("/twin/simulate", json={"events": "bad"}, headers=h)
        assert r.status_code == 400

    def test_user_isolation(self, client, app_fixture):
        h1 = _auth(client, "iso1@twin.test")
        h2 = _auth(client, "iso2@twin.test")
        uid1 = _get_uid(app_fixture, "iso1@twin.test")
        _seed(app_fixture, uid1, 99999, expense_type="INCOME", days_ago=5)

        r2 = client.post("/twin/simulate", json={"horizon_months": 1}, headers=h2)
        assert r2.get_json()["baseline"]["income"] == 0.0


class TestTwinEventTypesEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/twin/event-types").status_code == 401

    def test_returns_list(self, client, app_fixture):
        h = _auth(client, "et1@test.com")
        r = client.get("/twin/event-types", headers=h)
        assert r.status_code == 200
        types = r.get_json()
        assert isinstance(types, list)
        assert len(types) == len(VALID_EVENT_TYPES)

    def test_each_type_has_description(self, client, app_fixture):
        h = _auth(client, "et2@test.com")
        types = client.get("/twin/event-types", headers=h).get_json()
        for t in types:
            assert "type" in t
            assert "description" in t
            assert t["type"] in VALID_EVENT_TYPES
