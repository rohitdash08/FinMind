"""Tests for the advanced search endpoint."""
import pytest


def _create_expense(client, auth_header, **kwargs):
    payload = {
        "amount": kwargs.get("amount", "50.00"),
        "description": kwargs.get("description", "Test expense"),
        "date": kwargs.get("date", "2025-06-15"),
        "category_id": kwargs.get("category_id"),
    }
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _create_bill(client, auth_header, **kwargs):
    payload = {
        "name": kwargs.get("name", "Test bill"),
        "amount": kwargs.get("amount", 100),
        "next_due_date": kwargs.get("next_due_date", "2025-07-01"),
        "cadence": kwargs.get("cadence", "MONTHLY"),
    }
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _create_category(client, auth_header, name="Food"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


class TestSearchEndpoint:
    def test_search_requires_auth(self, client):
        r = client.get("/api/search")
        assert r.status_code in (401, 422)

    def test_search_empty(self, client, auth_header):
        r = client.get("/api/search", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["results"] == []
        assert data["total"] == 0

    def test_search_expenses_by_query(self, client, auth_header):
        _create_expense(client, auth_header, description="Grocery shopping")
        _create_expense(client, auth_header, description="Electric bill payment")

        r = client.get("/api/search?q=grocery", headers=auth_header)
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["type"] == "expense"
        assert "Grocery" in data["results"][0]["description"]

    def test_search_bills_by_query(self, client, auth_header):
        _create_bill(client, auth_header, name="Netflix subscription")
        _create_bill(client, auth_header, name="Gym membership")

        r = client.get("/api/search?q=netflix", headers=auth_header)
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["type"] == "bill"
        assert "Netflix" in data["results"][0]["description"]

    def test_search_type_filter(self, client, auth_header):
        _create_expense(client, auth_header, description="Netflix charge")
        _create_bill(client, auth_header, name="Netflix subscription")

        r = client.get("/api/search?q=netflix&type=expense", headers=auth_header)
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["type"] == "expense"

        r = client.get("/api/search?q=netflix&type=bill", headers=auth_header)
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["type"] == "bill"

    def test_search_amount_range(self, client, auth_header):
        _create_expense(client, auth_header, amount="25.00", description="Small item")
        _create_expense(client, auth_header, amount="150.00", description="Big item")

        r = client.get(
            "/api/search?type=expense&min_amount=100&max_amount=200",
            headers=auth_header,
        )
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["amount"] == 150.0

    def test_search_date_range(self, client, auth_header):
        _create_expense(client, auth_header, description="Jan item", date="2025-01-15")
        _create_expense(client, auth_header, description="Jun item", date="2025-06-15")

        r = client.get(
            "/api/search?type=expense&from_date=2025-06-01&to_date=2025-06-30",
            headers=auth_header,
        )
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["description"] == "Jun item"

    def test_search_pagination(self, client, auth_header):
        for i in range(5):
            _create_expense(client, auth_header, description=f"Item {i}", date=f"2025-06-{10+i:02d}")

        r = client.get("/api/search?type=expense&per_page=2&page=1", headers=auth_header)
        data = r.get_json()
        assert data["total"] == 5
        assert len(data["results"]) == 2
        assert data["page"] == 1
        assert data["per_page"] == 2

        r = client.get("/api/search?type=expense&per_page=2&page=3", headers=auth_header)
        data = r.get_json()
        assert len(data["results"]) == 1

    def test_search_combined_expenses_and_bills(self, client, auth_header):
        _create_expense(client, auth_header, description="Rent payment")
        _create_bill(client, auth_header, name="Rent reminder")

        r = client.get("/api/search?q=rent", headers=auth_header)
        data = r.get_json()
        assert data["total"] == 2
        types = {r["type"] for r in data["results"]}
        assert types == {"expense", "bill"}

    def test_search_invalid_pagination(self, client, auth_header):
        r = client.get("/api/search?page=abc", headers=auth_header)
        assert r.status_code == 400

    def test_search_results_sorted_by_date_desc(self, client, auth_header):
        _create_expense(client, auth_header, description="Old", date="2025-01-01")
        _create_expense(client, auth_header, description="New", date="2025-12-01")

        r = client.get("/api/search?type=expense", headers=auth_header)
        data = r.get_json()
        dates = [r["date"] for r in data["results"]]
        assert dates == sorted(dates, reverse=True)
