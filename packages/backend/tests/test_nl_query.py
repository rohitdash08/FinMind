"""
Tests for Natural Language Finance Query (Issue #74).

Covers:
- POST /query/ask returns correct structure
- Intent detection: spend / income / net_flow / count / top_categories / average
- Date range parsing: last week, last month, last quarter, last year, this month,
  this year, in [month name], in YYYY, in YYYY-MM
- Category matching from user's actual categories
- Unknown category → answer without filter
- answer_text is a non-empty string
- source_data populated
- confidence field present and valid
- anchor param accepted
- missing query returns 400
- query too long returns 400
- invalid anchor returns 400
- Auth required
- User isolation (queries only own data)
- GET /query/examples returns list
- Unit tests: _parse_date_range, _detect_intent, answer_query
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Category, Expense
from app.services.nl_query import _detect_intent, _parse_date_range, answer_query


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="nl@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


def _seed(app_fixture, uid, amount, expense_type="EXPENSE", days_ago=5,
          category_id=None, notes="x"):
    with app_fixture.app_context():
        db.session.add(Expense(
            user_id=uid, amount=Decimal(str(amount)), currency="INR",
            expense_type=expense_type,
            spent_at=date.today() - timedelta(days=days_ago),
            notes=notes, category_id=category_id,
        ))
        db.session.commit()


def _seed_category(app_fixture, uid, name):
    with app_fixture.app_context():
        cat = Category(user_id=uid, name=name)
        db.session.add(cat)
        db.session.commit()
        return cat.id


_ANCHOR = date(2026, 3, 17)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — _parse_date_range
# ─────────────────────────────────────────────────────────────────────────────

class TestParseDateRange:
    def test_last_week(self):
        start, end, label = _parse_date_range("last week", _ANCHOR)
        assert (end - start).days == 6
        assert "week" in label

    def test_last_month(self):
        start, end, label = _parse_date_range("last month", _ANCHOR)
        assert start.month == 2
        assert "month" in label.lower() or "february" in label.lower()

    def test_last_quarter(self):
        start, end, label = _parse_date_range("last quarter", _ANCHOR)
        assert "quarter" in label

    def test_last_year(self):
        start, end, label = _parse_date_range("last year", _ANCHOR)
        assert start.year == 2025
        assert end.year == 2025

    def test_this_month(self):
        start, end, label = _parse_date_range("this month", _ANCHOR)
        assert start == date(2026, 3, 1)

    def test_this_year(self):
        start, end, label = _parse_date_range("this year", _ANCHOR)
        assert start == date(2026, 1, 1)

    def test_in_year_month(self):
        start, end, label = _parse_date_range("in 2026-01", _ANCHOR)
        assert start == date(2026, 1, 1)

    def test_in_year(self):
        start, end, label = _parse_date_range("in 2025", _ANCHOR)
        assert start.year == 2025

    def test_in_month_name(self):
        start, end, label = _parse_date_range("in january", _ANCHOR)
        assert start.month == 1

    def test_default_this_month(self):
        start, end, label = _parse_date_range("how much did I spend?", _ANCHOR)
        assert start == date(_ANCHOR.year, _ANCHOR.month, 1)

    def test_last_n_days(self):
        start, end, label = _parse_date_range("last 14 days", _ANCHOR)
        assert (end - start).days == 14


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — _detect_intent
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectIntent:
    def test_spend_default(self):
        assert _detect_intent("how much did I spend on food") == "spend"

    def test_income_keyword(self):
        assert _detect_intent("how much did I earn last month") == "income"
        assert _detect_intent("what was my salary") == "income"

    def test_net_flow(self):
        assert _detect_intent("what is my net flow") == "net_flow"
        assert _detect_intent("how much did I save") == "net_flow"

    def test_count(self):
        assert _detect_intent("how many transactions last week") == "count"

    def test_top_categories(self):
        assert _detect_intent("show my top categories") == "top_categories"

    def test_average(self):
        assert _detect_intent("what is my average spending") == "average"


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — answer_query
# ─────────────────────────────────────────────────────────────────────────────

class TestAnswerQuery:
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
        uid = self._make_user(app_fixture, "aq_struct@test.com")
        with app_fixture.app_context():
            result = answer_query(uid, "how much did I spend this month")
        for k in ("query", "intent", "date_range", "category", "answer",
                  "answer_text", "source_data", "confidence"):
            assert k in result

    def test_spend_query_returns_zero_on_empty(self, app_fixture):
        uid = self._make_user(app_fixture, "aq_zero@test.com")
        with app_fixture.app_context():
            result = answer_query(uid, "how much did I spend this month")
        assert result["answer"] == 0.0
        assert isinstance(result["answer_text"], str)

    def test_income_query(self, app_fixture):
        uid = self._make_user(app_fixture, "aq_inc@test.com")
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid, amount=Decimal("5000"),
                                   currency="INR", expense_type="INCOME",
                                   spent_at=date.today() - timedelta(days=3), notes="s"))
            db.session.commit()
            result = answer_query(uid, "how much did I earn this month")
        assert result["answer"] == pytest.approx(5000.0, abs=1.0)
        assert result["intent"] == "income"

    def test_category_filter(self, app_fixture):
        uid = self._make_user(app_fixture, "aq_cat@test.com")
        with app_fixture.app_context():
            cat = Category(user_id=uid, name="Food")
            db.session.add(cat)
            db.session.commit()
            db.session.add(Expense(user_id=uid, amount=Decimal("300"),
                                   currency="INR", expense_type="EXPENSE",
                                   category_id=cat.id,
                                   spent_at=date.today() - timedelta(days=2), notes="lunch"))
            db.session.add(Expense(user_id=uid, amount=Decimal("1000"),
                                   currency="INR", expense_type="EXPENSE",
                                   category_id=None,
                                   spent_at=date.today() - timedelta(days=2), notes="other"))
            db.session.commit()
            result = answer_query(uid, "how much did I spend on Food this month")
        assert result["category"] == "Food"
        assert result["answer"] == pytest.approx(300.0, abs=1.0)

    def test_user_isolation(self, app_fixture):
        uid1 = self._make_user(app_fixture, "aq_iso1@test.com")
        uid2 = self._make_user(app_fixture, "aq_iso2@test.com")
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid1, amount=Decimal("9000"),
                                   currency="INR", expense_type="EXPENSE",
                                   spent_at=date.today() - timedelta(days=2), notes="big"))
            db.session.commit()
            result = answer_query(uid2, "how much did I spend this month")
        assert result["answer"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestQueryAskEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.post("/query/ask", json={"query": "spend"}).status_code == 401

    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "qa1@test.com")
        r = client.post("/query/ask",
                        json={"query": "how much did I spend this month"},
                        headers=h)
        assert r.status_code == 200

    def test_response_structure(self, client, app_fixture):
        h = _auth(client, "qa2@test.com")
        d = client.post("/query/ask",
                        json={"query": "how much did I spend"},
                        headers=h).get_json()
        for k in ("query", "intent", "date_range", "answer", "answer_text", "confidence"):
            assert k in d

    def test_missing_query_returns_400(self, client, app_fixture):
        h = _auth(client, "qa3@test.com")
        assert client.post("/query/ask", json={}, headers=h).status_code == 400

    def test_too_long_query_returns_400(self, client, app_fixture):
        h = _auth(client, "qa4@test.com")
        r = client.post("/query/ask", json={"query": "x" * 501}, headers=h)
        assert r.status_code == 400

    def test_invalid_anchor_returns_400(self, client, app_fixture):
        h = _auth(client, "qa5@test.com")
        r = client.post("/query/ask",
                        json={"query": "spend", "anchor": "bad-date"},
                        headers=h)
        assert r.status_code == 400

    def test_valid_anchor(self, client, app_fixture):
        h = _auth(client, "qa6@test.com")
        r = client.post("/query/ask",
                        json={"query": "how much did I spend last month",
                              "anchor": "2026-03-17"},
                        headers=h)
        assert r.status_code == 200

    def test_spend_query_answer_text_non_empty(self, client, app_fixture):
        h = _auth(client, "qa7@test.com")
        d = client.post("/query/ask",
                        json={"query": "how much did I spend last month"},
                        headers=h).get_json()
        assert len(d["answer_text"]) > 5

    def test_income_intent_detected(self, client, app_fixture):
        h = _auth(client, "qa8@test.com")
        d = client.post("/query/ask",
                        json={"query": "how much did I earn last month"},
                        headers=h).get_json()
        assert d["intent"] == "income"

    def test_top_categories_intent(self, client, app_fixture):
        h = _auth(client, "qa9@test.com")
        d = client.post("/query/ask",
                        json={"query": "show my top categories this month"},
                        headers=h).get_json()
        assert d["intent"] == "top_categories"

    def test_confidence_field_valid(self, client, app_fixture):
        h = _auth(client, "qa10@test.com")
        d = client.post("/query/ask",
                        json={"query": "how much did I spend"},
                        headers=h).get_json()
        assert d["confidence"] in ("high", "medium", "low")

    def test_user_isolation(self, client, app_fixture):
        h1 = _auth(client, "qa_iso1@test.com")
        h2 = _auth(client, "qa_iso2@test.com")
        uid1 = _get_uid(app_fixture, "qa_iso1@test.com")
        _seed(app_fixture, uid1, 7777, days_ago=3)

        d2 = client.post("/query/ask",
                         json={"query": "how much did I spend this month"},
                         headers=h2).get_json()
        assert d2["answer"] == 0.0


class TestQueryExamplesEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/query/examples").status_code == 401

    def test_returns_examples(self, client, app_fixture):
        h = _auth(client, "qe1@test.com")
        r = client.get("/query/examples", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert "examples" in d
        assert len(d["examples"]) >= 5
