"""Tests for locale-aware formatting."""

import pytest
from datetime import date
from app.services.locale_formatting import (
    get_locale, update_locale, format_currency, format_date,
    format_number, get_supported_currencies, get_date_formats, get_number_formats,
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


class TestLocale:
    def test_default(self, app, user):
        with app.app_context():
            loc = get_locale(user)
            assert loc["currency"] == "USD"
            assert loc["language"] == "en"

    def test_update(self, app, user):
        with app.app_context():
            loc = update_locale(user, currency="EUR", language="de", date_format="DD.MM.YYYY")
            assert loc["currency"] == "EUR"
            assert loc["date_format"] == "DD.MM.YYYY"

    def test_invalid_currency(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                update_locale(user, currency="XYZ")

    def test_invalid_date_format(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                update_locale(user, date_format="BAD")

    def test_invalid_number_format(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                update_locale(user, number_format="BAD")


class TestFormatCurrency:
    def test_usd(self, app, user):
        with app.app_context():
            get_locale(user)
            assert format_currency(user, 1234.56) == "$1,234.56"

    def test_eur(self, app, user):
        with app.app_context():
            update_locale(user, currency="EUR", number_format="1.234,56")
            assert format_currency(user, 1234.56) == "€1.234,56"

    def test_cny(self, app, user):
        with app.app_context():
            update_locale(user, currency="CNY")
            assert format_currency(user, 99.9) == "¥99.90"

    def test_negative(self, app, user):
        with app.app_context():
            get_locale(user)
            assert format_currency(user, -50) == "$-50.00"


class TestFormatDate:
    def test_iso(self, app, user):
        with app.app_context():
            get_locale(user)
            assert format_date(user, date(2026, 2, 27)) == "2026-02-27"

    def test_us(self, app, user):
        with app.app_context():
            update_locale(user, date_format="MM/DD/YYYY")
            assert format_date(user, date(2026, 2, 27)) == "02/27/2026"

    def test_eu(self, app, user):
        with app.app_context():
            update_locale(user, date_format="DD/MM/YYYY")
            assert format_date(user, date(2026, 2, 27)) == "27/02/2026"

    def test_chinese(self, app, user):
        with app.app_context():
            update_locale(user, date_format="YYYY年MM月DD日")
            assert format_date(user, date(2026, 2, 27)) == "2026年02月27日"


class TestFormatNumber:
    def test_default(self, app, user):
        with app.app_context():
            get_locale(user)
            assert format_number(user, 1234567.89) == "1,234,567.89"

    def test_european(self, app, user):
        with app.app_context():
            update_locale(user, number_format="1.234,56")
            assert format_number(user, 1234567.89) == "1.234.567,89"

    def test_swiss(self, app, user):
        with app.app_context():
            update_locale(user, number_format="1'234.56")
            assert format_number(user, 1234.5) == "1'234.50"


class TestCatalogs:
    def test_currencies(self, app):
        with app.app_context():
            c = get_supported_currencies()
            assert len(c) >= 5
            assert any(x["code"] == "USD" for x in c)

    def test_date_formats(self, app):
        with app.app_context():
            assert len(get_date_formats()) >= 4

    def test_number_formats(self, app):
        with app.app_context():
            assert len(get_number_formats()) >= 3


class TestAPI:
    def test_get(self, app, user, token):
        client = app.test_client()
        resp = client.get("/locale/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_update(self, app, user, token):
        client = app.test_client()
        resp = client.put("/locale/", json={"currency": "GBP"},
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_format_currency(self, app, user, token):
        client = app.test_client()
        resp = client.post("/locale/format/currency", json={"amount": 99.99},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_format_date(self, app, user, token):
        client = app.test_client()
        resp = client.post("/locale/format/date", json={"date": "2026-02-27"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_format_number(self, app, user, token):
        client = app.test_client()
        resp = client.post("/locale/format/number", json={"value": 1234.5},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_currencies(self, app, user, token):
        client = app.test_client()
        resp = client.get("/locale/currencies", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
