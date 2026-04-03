"""Tests for Natural Language Finance Query (issue #74)."""
from datetime import date
import pytest
from flask_jwt_extended import create_access_token

from app.services.nl_query import parse_date_range, extract_category


@pytest.fixture()
def auth_header(app_fixture):
    with app_fixture.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        user = User(email="nltest@test.com", password_hash=generate_password_hash("Pass1234!"))
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
        return {"Authorization": f"Bearer {token}"}


class TestDateParsing:
    TODAY = date(2026, 4, 3)

    def test_default_last_30_days(self):
        start, end = parse_date_range("what did I spend", self.TODAY)
        assert (end - start).days == 29

    def test_last_7_days(self):
        start, end = parse_date_range("spending last 7 days", self.TODAY)
        assert (end - start).days == 6

    def test_last_quarter(self):
        start, end = parse_date_range("last quarter spending", self.TODAY)
        assert start.month == 1
        assert end.month == 3

    def test_this_month(self):
        start, end = parse_date_range("this month spending", self.TODAY)
        assert start.month == self.TODAY.month
        assert start.day == 1

    def test_last_month(self):
        start, end = parse_date_range("last month total", self.TODAY)
        assert start.month == 3
        assert end.month == 3

    def test_this_year(self):
        start, end = parse_date_range("this year summary", self.TODAY)
        assert start == date(2026, 1, 1)

    def test_specific_quarter_year(self):
        start, end = parse_date_range("q1 2025", self.TODAY)
        assert start == date(2025, 1, 1)
        assert end == date(2025, 3, 31)

    def test_specific_month_name(self):
        start, end = parse_date_range("in january", self.TODAY)
        assert start.month == 1
        assert start.day == 1

    def test_last_2_weeks(self):
        start, end = parse_date_range("last 2 weeks", self.TODAY)
        assert (end - start).days == 13

    def test_q4_2024(self):
        start, end = parse_date_range("q4 2024", self.TODAY)
        assert start == date(2024, 10, 1)
        assert end == date(2024, 12, 31)

    def test_last_year(self):
        start, end = parse_date_range("last year total", self.TODAY)
        assert start.year == 2025
        assert end.year == 2025


class TestCategoryExtraction:
    def test_food_category(self):
        assert extract_category("how much on food") == "food"

    def test_groceries_maps_to_food(self):
        assert extract_category("grocery spending") == "food"

    def test_restaurant_maps_to_food(self):
        assert extract_category("restaurant bills") == "food"

    def test_transport_category(self):
        assert extract_category("uber and taxi expenses") == "transport"

    def test_fuel_maps_to_transport(self):
        assert extract_category("fuel costs last month") == "transport"

    def test_entertainment_category(self):
        assert extract_category("netflix subscription") == "entertainment"

    def test_health_category(self):
        assert extract_category("medical expenses") == "health"

    def test_gym_maps_to_health(self):
        assert extract_category("gym membership") == "health"

    def test_shopping_category(self):
        assert extract_category("amazon purchases") == "shopping"

    def test_bills_category(self):
        assert extract_category("electricity and water bills") == "bills"

    def test_no_category_returns_none(self):
        assert extract_category("total spending last month") is None

    def test_education_category(self):
        assert extract_category("course fees this month") == "education"


class TestNLQueryAPI:
    def test_query_returns_structured_result(self, client, auth_header):
        resp = client.post("/query/", json={"query": "how much did I spend last month"}, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total" in data
        assert "transaction_count" in data
        assert "interpreted" in data
        assert "start_date" in data["interpreted"]
        assert "end_date" in data["interpreted"]

    def test_query_missing_returns_400(self, client, auth_header):
        resp = client.post("/query/", json={}, headers=auth_header)
        assert resp.status_code == 400

    def test_query_too_long_returns_400(self, client, auth_header):
        resp = client.post("/query/", json={"query": "x" * 501}, headers=auth_header)
        assert resp.status_code == 400

    def test_parse_endpoint(self, client, auth_header):
        resp = client.post("/query/parse", json={"query": "food spending last quarter"}, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["interpreted"]["category"] == "food"

    def test_query_empty_for_new_user(self, client, auth_header):
        resp = client.post("/query/", json={"query": "total spending this month"}, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0.0
        assert data["transactions"] == []

    def test_requires_auth(self, client):
        resp = client.post("/query/", json={"query": "spending"})
        assert resp.status_code == 401

    def test_category_interpreted_in_result(self, client, auth_header):
        resp = client.post("/query/", json={"query": "food spending last month"}, headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["interpreted"]["category"] == "food"
