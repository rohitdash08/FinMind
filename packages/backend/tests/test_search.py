"""Tests for advanced search across transactions and bills."""

import pytest
from datetime import date, timedelta


# ─── Helper ────────────────────────────────────────────────────────────


def _create_category(client, auth_header, name="Food"):
    r = client.post(
        "/categories",
        json={"name": name, "monthly_budget": 500},
        headers=auth_header,
    )
    assert r.status_code in (200, 201)
    return r.get_json()["id"]


def _create_expense(client, auth_header, notes="Lunch", amount=12.50,
                     category_id=None, expense_type="EXPENSE",
                     spent_at=None):
    payload = {
        "notes": notes,
        "amount": amount,
        "currency": "USD",
        "expense_type": expense_type,
    }
    if category_id:
        payload["category_id"] = category_id
    if spent_at:
        payload["spent_at"] = spent_at
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code in (200, 201), f"create expense fail: {r.get_json()}"
    return r.get_json()


def _create_bill(client, auth_header, name="Netflix", amount=15.99,
                  cadence="MONTHLY", due_date=None):
    if due_date is None:
        due_date = "2024-07-01"
    payload = {
        "name": name,
        "amount": amount,
        "cadence": cadence,
        "currency": "USD",
        "next_due_date": due_date,
    }
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code in (200, 201), f"create bill fail: {r.get_json()}"
    return r.get_json()


# ─── /search endpoint ──────────────────────────────────────────────────


class TestSearchEndpoint:
    """Tests for GET /search."""

    def test_search_no_params(self, client, auth_header):
        """Search with no params returns empty results."""
        r = client.get("/search", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 0
        assert data["results"] == []

    def test_search_returns_expenses(self, client, auth_header):
        """Search finds expenses by notes."""
        _create_expense(client, auth_header, notes="Starbucks coffee")
        _create_expense(client, auth_header, notes="Grocery run")

        r = client.get("/search?q=starbucks", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Starbucks coffee"
        assert data["results"][0]["type"] == "expense"

    def test_search_case_insensitive(self, client, auth_header):
        """Search is case-insensitive."""
        _create_expense(client, auth_header, notes="Amazon Purchase")

        r = client.get("/search?q=AMAZON", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] == 1

        r = client.get("/search?q=amazon", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] == 1

    def test_search_returns_bills(self, client, auth_header):
        """Search finds bills by name."""
        _create_bill(client, auth_header, name="Spotify Premium")

        r = client.get("/search?q=spotify", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["type"] == "bill"

    def test_search_by_category(self, client, auth_header):
        """Search filters by category_id."""
        cat_id = _create_category(client, auth_header, "Transport")
        _create_expense(client, auth_header, notes="Uber ride", category_id=cat_id)
        _create_expense(client, auth_header, notes="Pizza delivery")

        r = client.get(f"/search?category_id={cat_id}", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Uber ride"

    def test_search_by_amount_range(self, client, auth_header):
        """Search filters by amount_min and amount_max."""
        _create_expense(client, auth_header, notes="Small", amount=5.0)
        _create_expense(client, auth_header, notes="Medium", amount=50.0)
        _create_expense(client, auth_header, notes="Large", amount=500.0)

        r = client.get("/search?amount_min=10&amount_max=100", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Medium"

    def test_search_by_amount_min_only(self, client, auth_header):
        """Search with only amount_min."""
        _create_expense(client, auth_header, notes="Cheap", amount=3.0)
        _create_expense(client, auth_header, notes="Expensive", amount=300.0)

        r = client.get("/search?amount_min=100", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Expensive"

    def test_search_by_amount_max_only(self, client, auth_header):
        """Search with only amount_max."""
        _create_expense(client, auth_header, notes="Cheap", amount=3.0)
        _create_expense(client, auth_header, notes="Expensive", amount=300.0)

        r = client.get("/search?amount_max=10", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Cheap"

    def test_search_by_date_range(self, client, auth_header):
        """Search filters by date range."""
        _create_expense(client, auth_header, notes="Old", spent_at="2024-01-15")
        _create_expense(client, auth_header, notes="Recent", spent_at="2024-06-15")
        _create_expense(client, auth_header, notes="Future", spent_at="2024-12-15")

        r = client.get(
            "/search?date_from=2024-06-01&date_to=2024-07-01&types=expenses",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Recent"

    def test_search_by_expense_type(self, client, auth_header):
        """Search filters by expense type."""
        _create_expense(client, auth_header, notes="Salary", amount=5000, expense_type="INCOME")
        _create_expense(client, auth_header, notes="Lunch", amount=12, expense_type="EXPENSE")

        r = client.get("/search?expense_type=INCOME&types=expenses", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Salary"

    def test_search_entity_type_filter(self, client, auth_header):
        """Search filters by entity types."""
        _create_expense(client, auth_header, notes="Coffee")
        _create_bill(client, auth_header, name="Electric")

        # Only expenses
        r = client.get("/search?types=expenses", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        for item in data["results"]:
            assert item["type"] == "expense"

        # Only bills
        r = client.get("/search?types=bills", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        for item in data["results"]:
            assert item["type"] == "bill"

    def test_search_combined_filters(self, client, auth_header):
        """Search with multiple filters combined."""
        cat_id = _create_category(client, auth_header, "Dining")
        _create_expense(client, auth_header, notes="Fancy dinner", amount=80,
                         category_id=cat_id, spent_at="2024-06-15")
        _create_expense(client, auth_header, notes="Quick lunch", amount=15,
                         category_id=cat_id, spent_at="2024-06-15")
        _create_expense(client, auth_header, notes="Cheap snack", amount=5,
                         spent_at="2024-06-15")

        r = client.get(
            f"/search?q=&category_id={cat_id}&amount_min=20&types=expenses",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "Fancy dinner"

    def test_search_sort_by_amount_asc(self, client, auth_header):
        """Search sorts by amount ascending."""
        _create_expense(client, auth_header, notes="C", amount=30)
        _create_expense(client, auth_header, notes="A", amount=10)
        _create_expense(client, auth_header, notes="B", amount=20)

        r = client.get(
            "/search?sort_by=amount&sort_order=asc&types=expenses",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        amounts = [r["amount"] for r in data["results"]]
        assert amounts == sorted(amounts)

    def test_search_sort_by_amount_desc(self, client, auth_header):
        """Search sorts by amount descending."""
        _create_expense(client, auth_header, notes="C", amount=30)
        _create_expense(client, auth_header, notes="A", amount=10)
        _create_expense(client, auth_header, notes="B", amount=20)

        r = client.get(
            "/search?sort_by=amount&sort_order=desc&types=expenses",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        amounts = [r["amount"] for r in data["results"]]
        assert amounts == sorted(amounts, reverse=True)

    def test_search_sort_by_name(self, client, auth_header):
        """Search sorts by name."""
        _create_expense(client, auth_header, notes="Zara")
        _create_expense(client, auth_header, notes="Apple")
        _create_expense(client, auth_header, notes="Mango")

        r = client.get(
            "/search?sort_by=name&sort_order=asc&types=expenses",
            headers=auth_header,
        )
        assert r.status_code == 200
        data = r.get_json()
        names = [r["name"] for r in data["results"]]
        assert names == sorted(names, key=str.lower)

    def test_search_pagination(self, client, auth_header):
        """Search supports pagination."""
        for i in range(15):
            _create_expense(client, auth_header, notes=f"Item {i:02d}", amount=i + 1)

        # Page 1 with page_size=5
        r = client.get("/search?page=1&page_size=5&types=expenses", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["results"]) == 5
        assert data["total"] == 15
        assert data["total_pages"] == 3
        assert data["has_more"] is True

        # Page 3
        r = client.get("/search?page=3&page_size=5&types=expenses", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["results"]) == 5
        assert data["has_more"] is False

    def test_search_invalid_sort_by(self, client, auth_header):
        """Invalid sort_by returns 400."""
        r = client.get("/search?sort_by=invalid", headers=auth_header)
        assert r.status_code == 400

    def test_search_invalid_sort_order(self, client, auth_header):
        """Invalid sort_order returns 400."""
        r = client.get("/search?sort_order=random", headers=auth_header)
        assert r.status_code == 400

    def test_search_invalid_page(self, client, auth_header):
        """Negative page returns 400."""
        r = client.get("/search?page=0", headers=auth_header)
        assert r.status_code == 400

    def test_search_invalid_page_size(self, client, auth_header):
        """page_size > 200 returns 400."""
        r = client.get("/search?page_size=500", headers=auth_header)
        assert r.status_code == 400

    def test_search_multi_entity_types(self, client, auth_header):
        """Search across multiple entity types."""
        _create_expense(client, auth_header, notes="Netflix sub")
        _create_bill(client, auth_header, name="Netflix bill")

        r = client.get("/search?q=netflix&types=expenses,bills", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 2
        types = {r["type"] for r in data["results"]}
        assert types == {"expense", "bill"}

    def test_search_partial_match(self, client, auth_header):
        """Search matches partial text."""
        _create_expense(client, auth_header, notes="Whole Foods Market")

        r = client.get("/search?q=whole", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] >= 1

        r = client.get("/search?q=foods", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] >= 1

    def test_search_no_match(self, client, auth_header):
        """Search with no matches returns empty."""
        _create_expense(client, auth_header, notes="Coffee")

        r = client.get("/search?q=xyznonexistent", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] == 0

    def test_search_result_structure(self, client, auth_header):
        """Verify search result has expected fields."""
        cat_id = _create_category(client, auth_header, "Food")
        _create_expense(client, auth_header, notes="Test expense",
                         amount=25.50, category_id=cat_id)

        r = client.get("/search?q=test&types=expenses", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1

        item = data["results"][0]
        assert "id" in item
        assert item["type"] == "expense"
        assert item["name"] == "Test expense"
        assert item["amount"] == 25.50
        assert item["currency"] == "USD"
        assert item["category"] == "Food"
        assert item["category_id"] == cat_id

    def test_search_bill_result_structure(self, client, auth_header):
        """Verify bill search result has expected fields."""
        _create_bill(client, auth_header, name="Phone bill", amount=45.0)

        r = client.get("/search?q=phone&types=bills", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1

        item = data["results"][0]
        assert "id" in item
        assert item["type"] == "bill"
        assert item["name"] == "Phone bill"
        assert item["amount"] == 45.0
        assert "cadence" in item


# ─── /search/suggestions endpoint ──────────────────────────────────────


class TestSuggestionsEndpoint:
    """Tests for GET /search/suggestions."""

    def test_suggestions_basic(self, client, auth_header):
        """Suggestions returns matching expense notes."""
        _create_expense(client, auth_header, notes="Starbucks Latte")
        _create_expense(client, auth_header, notes="Subway Sandwich")

        r = client.get("/search/suggestions?q=sta", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["suggestions"]) >= 1
        texts = [s["text"] for s in data["suggestions"]]
        assert "Starbucks Latte" in texts

    def test_suggestions_too_short(self, client, auth_header):
        """Prefix shorter than 2 chars returns empty."""
        r = client.get("/search/suggestions?q=a", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["suggestions"] == []

    def test_suggestions_empty(self, client, auth_header):
        """Empty prefix returns empty."""
        r = client.get("/search/suggestions?q=", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["suggestions"] == []

    def test_suggestions_includes_bills(self, client, auth_header):
        """Suggestions include bill names."""
        _create_bill(client, auth_header, name="Netflix Premium")

        r = client.get("/search/suggestions?q=net", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        texts = [s["text"] for s in data["suggestions"]]
        assert "Netflix Premium" in texts

    def test_suggestions_includes_categories(self, client, auth_header):
        """Suggestions include category names."""
        _create_category(client, auth_header, "Transportation")

        r = client.get("/search/suggestions?q=trans", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        texts = [s["text"] for s in data["suggestions"]]
        assert "Transportation" in texts

    def test_suggestions_limit(self, client, auth_header):
        """Suggestions respects limit parameter."""
        for i in range(20):
            _create_expense(client, auth_header, notes=f"Test item {i}")

        r = client.get("/search/suggestions?q=test&limit=5", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()["suggestions"]) <= 5

    def test_suggestions_invalid_limit(self, client, auth_header):
        """Limit > 50 returns 400."""
        r = client.get("/search/suggestions?q=test&limit=100", headers=auth_header)
        assert r.status_code == 400

    def test_suggestions_deduplicates(self, client, auth_header):
        """Suggestions deduplicates same text from different sources."""
        _create_expense(client, auth_header, notes="Coffee Shop")
        _create_expense(client, auth_header, notes="Coffee Shop")

        r = client.get("/search/suggestions?q=coffee", headers=auth_header)
        assert r.status_code == 200
        texts = [s["text"] for s in r.get_json()["suggestions"]]
        assert texts.count("Coffee Shop") <= 1


# ─── /search/stats endpoint ────────────────────────────────────────────


class TestStatsEndpoint:
    """Tests for GET /search/stats."""

    def test_stats_empty(self, client, auth_header):
        """Stats for user with no data."""
        r = client.get("/search/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["expense_count"] == 0
        assert data["bill_count"] == 0
        assert data["total_searchable"] == 0

    def test_stats_with_data(self, client, auth_header):
        """Stats reflects created data."""
        _create_expense(client, auth_header, notes="A")
        _create_expense(client, auth_header, notes="B")
        _create_bill(client, auth_header, name="C")
        _create_category(client, auth_header, "D")

        r = client.get("/search/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["expense_count"] == 2
        assert data["bill_count"] == 1
        assert data["category_count"] >= 1
        assert data["total_searchable"] >= 3

    def test_stats_date_range(self, client, auth_header):
        """Stats includes date range."""
        _create_expense(client, auth_header, notes="Old", spent_at="2024-01-01")
        _create_expense(client, auth_header, notes="New", spent_at="2024-12-31")

        r = client.get("/search/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["date_range"]["earliest"] is not None
        assert data["date_range"]["latest"] is not None


# ─── Authentication tests ──────────────────────────────────────────────


class TestSearchAuth:
    """Tests that search endpoints require authentication."""

    def test_search_requires_auth(self, client):
        r = client.get("/search")
        assert r.status_code in (401, 422)

    def test_suggestions_requires_auth(self, client):
        r = client.get("/search/suggestions?q=test")
        assert r.status_code in (401, 422)

    def test_stats_requires_auth(self, client):
        r = client.get("/search/stats")
        assert r.status_code in (401, 422)
