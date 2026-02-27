"""Tests for multi-currency expense tracking."""

import pytest
from datetime import date
from app.services.multi_currency import (
    get_user_currency, set_user_currency, set_exchange_rate,
    get_exchange_rate, convert_amount, list_rates, multi_currency_summary,
)


@pytest.fixture
def app():
    from app import create_app
    from app.config import Settings
    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    app = create_app(settings)
    with app.app_context():
        from app.extensions import db
        db.create_all()
        yield app


@pytest.fixture
def user(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        u = User(email="test@example.com", password_hash=generate_password_hash("pass"))
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def token(app, user):
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(identity=str(user))


@pytest.fixture
def rates(app):
    with app.app_context():
        set_exchange_rate("USD", "EUR", 0.92)
        set_exchange_rate("USD", "GBP", 0.79)
        set_exchange_rate("USD", "JPY", 149.5)


class TestUserCurrency:
    def test_default(self, app, user):
        with app.app_context():
            pref = get_user_currency(user)
            assert pref["base_currency"] == "USD"

    def test_set(self, app, user):
        with app.app_context():
            pref = set_user_currency(user, "EUR", ["USD", "GBP"])
            assert pref["base_currency"] == "EUR"
            assert "USD" in pref["display_currencies"]

    def test_invalid_code(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                set_user_currency(user, "EURO")


class TestExchangeRate:
    def test_set_and_get(self, app):
        with app.app_context():
            set_exchange_rate("USD", "EUR", 0.92)
            rate = get_exchange_rate("USD", "EUR")
            assert rate == 0.92

    def test_same_currency(self, app):
        with app.app_context():
            assert get_exchange_rate("USD", "USD") == 1.0

    def test_inverse(self, app, rates):
        with app.app_context():
            rate = get_exchange_rate("EUR", "USD")
            assert rate is not None
            assert abs(rate - 1 / 0.92) < 0.001

    def test_not_found(self, app):
        with app.app_context():
            assert get_exchange_rate("XYZ", "ABC") is None

    def test_update_existing(self, app):
        with app.app_context():
            set_exchange_rate("USD", "EUR", 0.90)
            set_exchange_rate("USD", "EUR", 0.95)
            assert get_exchange_rate("USD", "EUR") == 0.95

    def test_negative_rate(self, app):
        with app.app_context():
            with pytest.raises(ValueError):
                set_exchange_rate("USD", "EUR", -1)

    def test_list_rates(self, app, rates):
        with app.app_context():
            all_rates = list_rates()
            assert len(all_rates) == 3

    def test_list_by_base(self, app, rates):
        with app.app_context():
            usd_rates = list_rates(base="USD")
            assert all(r["base_currency"] == "USD" for r in usd_rates)


class TestConvert:
    def test_basic(self, app, rates):
        with app.app_context():
            result = convert_amount(100, "USD", "EUR")
            assert result["converted"] == 92.0
            assert result["rate"] == 0.92

    def test_same_currency(self, app):
        with app.app_context():
            result = convert_amount(100, "USD", "USD")
            assert result["converted"] == 100

    def test_no_rate(self, app):
        with app.app_context():
            with pytest.raises(ValueError):
                convert_amount(100, "XYZ", "ABC")


class TestSummary:
    def test_basic(self, app, user, rates):
        with app.app_context():
            expenses = [
                {"amount": 100, "currency": "USD", "description": "lunch"},
                {"amount": 50, "currency": "EUR", "description": "dinner"},
            ]
            result = multi_currency_summary(user, expenses)
            assert result["base_currency"] == "USD"
            assert result["total_in_base"] > 0
            assert len(result["by_currency"]) == 2

    def test_missing_rate(self, app, user):
        with app.app_context():
            expenses = [{"amount": 100, "currency": "XYZ"}]
            result = multi_currency_summary(user, expenses)
            assert len(result["conversion_errors"]) > 0


class TestAPI:
    def test_get_preference(self, app, user, token):
        client = app.test_client()
        resp = client.get("/currency/preference", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_set_preference(self, app, user, token):
        client = app.test_client()
        resp = client.put(
            "/currency/preference",
            json={"base_currency": "EUR"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_add_rate(self, app, user, token):
        client = app.test_client()
        resp = client.post(
            "/currency/rates",
            json={"base_currency": "USD", "target_currency": "EUR", "rate": 0.92},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    def test_get_rates(self, app, user, token, rates):
        client = app.test_client()
        resp = client.get("/currency/rates", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_convert(self, app, user, token, rates):
        client = app.test_client()
        resp = client.post(
            "/currency/convert",
            json={"amount": 100, "from_currency": "USD", "to_currency": "EUR"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["converted"] == 92.0

    def test_summary(self, app, user, token, rates):
        client = app.test_client()
        resp = client.post(
            "/currency/summary",
            json={"expenses": [{"amount": 100, "currency": "USD"}]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
