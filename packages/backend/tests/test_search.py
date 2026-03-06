"""Tests for the advanced search endpoint ``GET /search``."""

import pytest
from datetime import date


def _create_category(client, headers, name="Groceries"):
    r = client.post("/categories", json={"name": name}, headers=headers)
    assert r.status_code == 201
    return r.get_json()["id"]


def _create_expense(client, headers, **overrides):
    payload = {
        "amount": 50.00,
        "description": "Test expense",
        "date": "2026-01-15",
        "expense_type": "EXPENSE",
    }
    payload.update(overrides)
    r = client.post("/expenses", json=payload, headers=headers)
    assert r.status_code == 201
    return r.get_json()


def _create_bill(client, headers, **overrides):
    payload = {
        "name": "Netflix",
        "amount": 15.99,
        "next_due_date": "2026-02-01",
        "cadence": "MONTHLY",
    }
    payload.update(overrides)
    r = client.post("/bills", json=payload, headers=headers)
    assert r.status_code == 201
    return r.get_json()


class TestSearchBasic:
    """Basic search functionality."""

    def test_search_requires_auth(self, client):
        r = client.get("/search")
        assert r.status_code in (401, 422)

    def test_empty_search_returns_structure(self, client, auth_header):
        r = client.get("/search", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "results" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "expense_count" in data
        assert "bill_count" in data

    def test_search_returns_expenses_and_bills(self, client, auth_header):
        _create_expense(client, auth_header, description="Coffee at Starbucks")
        _create_bill(client, auth_header, name="Spotify")

        r = client.get("/search", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 2
        assert data["expense_count"] == 1
        assert data["bill_count"] == 1

        types = {item["result_type"] for item in data["results"]}
        assert types == {"expense", "bill"}


class TestSearchTextQuery:
    """Free-text query (q parameter)."""

    def test_q_matches_expense_description(self, client, auth_header):
        _create_expense(client, auth_header, description="Coffee at Starbucks")
        _create_expense(client, auth_header, description="Lunch at subway")

        r = client.get("/search?q=coffee", headers=auth_header)
        data = r.get_json()
        assert data["expense_count"] == 1
        assert data["results"][0]["description"] == "Coffee at Starbucks"

    def test_q_matches_bill_name(self, client, auth_header):
        _create_bill(client, auth_header, name="Netflix Premium")
        _create_bill(client, auth_header, name="Spotify Family")

        r = client.get("/search?q=netflix", headers=auth_header)
        data = r.get_json()
        assert data["bill_count"] == 1
        assert data["results"][0]["description"] == "Netflix Premium"

    def test_q_matches_category_name(self, client, auth_header):
        cat_id = _create_category(client, auth_header, name="Entertainment")
        _create_expense(
            client, auth_header, description="Movie tickets",
            category_id=cat_id,
        )
        _create_expense(client, auth_header, description="Bus fare")

        r = client.get("/search?q=entertainment", headers=auth_header)
        data = r.get_json()
        assert data["expense_count"] == 1
        assert data["results"][0]["category_name"] == "Entertainment"

    def test_q_case_insensitive(self, client, auth_header):
        _create_expense(client, auth_header, description="UBER ride")

        r = client.get("/search?q=uber", headers=auth_header)
        assert r.get_json()["expense_count"] == 1

        r = client.get("/search?q=UBER", headers=auth_header)
        assert r.get_json()["expense_count"] == 1


class TestSearchFilters:
    """Filter parameters: category, amount, date, expense_type."""

    def test_filter_by_category_id(self, client, auth_header):
        cat_id = _create_category(client, auth_header, name="Food")
        _create_expense(
            client, auth_header, description="Pizza",
            category_id=cat_id,
        )
        _create_expense(client, auth_header, description="Gas")

        r = client.get(f"/search?category_id={cat_id}", headers=auth_header)
        data = r.get_json()
        assert data["expense_count"] == 1
        assert data["results"][0]["category_name"] == "Food"

    def test_filter_by_category_name(self, client, auth_header):
        cat_id = _create_category(client, auth_header, name="Transport")
        _create_expense(
            client, auth_header, description="Taxi",
            category_id=cat_id,
        )
        _create_expense(client, auth_header, description="Lunch")

        r = client.get("/search?category=transport", headers=auth_header)
        data = r.get_json()
        assert data["expense_count"] == 1

    def test_filter_by_amount_range(self, client, auth_header):
        _create_expense(client, auth_header, amount=10.00, description="Small")
        _create_expense(client, auth_header, amount=100.00, description="Big")
        _create_expense(client, auth_header, amount=50.00, description="Medium")

        r = client.get("/search?amount_min=40&amount_max=60", headers=auth_header)
        data = r.get_json()
        assert data["expense_count"] == 1
        assert data["results"][0]["description"] == "Medium"

    def test_filter_by_date_range(self, client, auth_header):
        _create_expense(
            client, auth_header, description="Jan expense", date="2026-01-10",
        )
        _create_expense(
            client, auth_header, description="Feb expense", date="2026-02-15",
        )

        r = client.get("/search?from=2026-02-01&to=2026-02-28", headers=auth_header)
        data = r.get_json()
        assert data["expense_count"] == 1
        assert data["results"][0]["description"] == "Feb expense"

    def test_filter_by_expense_type(self, client, auth_header):
        _create_expense(
            client, auth_header, description="Salary",
            expense_type="INCOME", amount=5000,
        )
        _create_expense(
            client, auth_header, description="Rent",
            expense_type="EXPENSE", amount=1200,
        )

        r = client.get("/search?expense_type=INCOME", headers=auth_header)
        data = r.get_json()
        assert data["expense_count"] == 1
        assert data["results"][0]["description"] == "Salary"


class TestSearchTypeFilter:
    """type parameter to restrict result types."""

    def test_type_expenses_only(self, client, auth_header):
        _create_expense(client, auth_header, description="Coffee")
        _create_bill(client, auth_header, name="Netflix")

        r = client.get("/search?type=expenses", headers=auth_header)
        data = r.get_json()
        assert data["expense_count"] == 1
        assert data["bill_count"] == 0

    def test_type_bills_only(self, client, auth_header):
        _create_expense(client, auth_header, description="Coffee")
        _create_bill(client, auth_header, name="Netflix")

        r = client.get("/search?type=bills", headers=auth_header)
        data = r.get_json()
        assert data["expense_count"] == 0
        assert data["bill_count"] == 1

    def test_invalid_type_returns_400(self, client, auth_header):
        r = client.get("/search?type=invalid", headers=auth_header)
        assert r.status_code == 400


class TestSearchSortingAndPagination:
    """Sorting and pagination."""

    def test_sort_by_amount_asc(self, client, auth_header):
        _create_expense(client, auth_header, amount=100, description="Big")
        _create_expense(client, auth_header, amount=10, description="Small")
        _create_expense(client, auth_header, amount=50, description="Medium")

        r = client.get("/search?sort=amount&order=asc&type=expenses", headers=auth_header)
        data = r.get_json()
        amounts = [item["amount"] for item in data["results"]]
        assert amounts == sorted(amounts)

    def test_sort_by_name(self, client, auth_header):
        _create_expense(client, auth_header, description="Zebra rent")
        _create_expense(client, auth_header, description="Apple store")

        r = client.get(
            "/search?sort=name&order=asc&type=expenses", headers=auth_header,
        )
        data = r.get_json()
        names = [item["description"] for item in data["results"]]
        assert names == sorted(names, key=str.lower)

    def test_pagination(self, client, auth_header):
        for i in range(5):
            _create_expense(
                client, auth_header, description=f"Item {i}", amount=float(i + 1),
            )

        r = client.get(
            "/search?type=expenses&page=1&page_size=2&sort=amount&order=asc",
            headers=auth_header,
        )
        data = r.get_json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["results"]) == 2

        r2 = client.get(
            "/search?type=expenses&page=3&page_size=2&sort=amount&order=asc",
            headers=auth_header,
        )
        data2 = r2.get_json()
        assert len(data2["results"]) == 1  # last page

    def test_invalid_sort_returns_400(self, client, auth_header):
        r = client.get("/search?sort=invalid", headers=auth_header)
        assert r.status_code == 400

    def test_invalid_order_returns_400(self, client, auth_header):
        r = client.get("/search?order=sideways", headers=auth_header)
        assert r.status_code == 400


class TestSearchCombined:
    """Combined filter + text scenarios."""

    def test_q_with_amount_filter(self, client, auth_header):
        _create_expense(
            client, auth_header, description="Coffee small", amount=3.50,
        )
        _create_expense(
            client, auth_header, description="Coffee large", amount=7.00,
        )
        _create_expense(
            client, auth_header, description="Tea", amount=2.50,
        )

        r = client.get("/search?q=coffee&amount_min=5", headers=auth_header)
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["description"] == "Coffee large"

    def test_q_with_date_and_type_filter(self, client, auth_header):
        _create_expense(
            client, auth_header, description="Coffee Jan",
            date="2026-01-10",
        )
        _create_expense(
            client, auth_header, description="Coffee Feb",
            date="2026-02-10",
        )
        _create_bill(client, auth_header, name="Coffee subscription")

        r = client.get(
            "/search?q=coffee&from=2026-02-01&type=expenses",
            headers=auth_header,
        )
        data = r.get_json()
        assert data["expense_count"] == 1
        assert data["bill_count"] == 0
        assert data["results"][0]["description"] == "Coffee Feb"
