"""Tests for essential vs discretionary spending breakdown (#120)."""


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    return next(c["id"] for c in r.get_json() if c["name"] == name)


def _create_expense(client, auth_header, amount, description, category_id, date_str):
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "description": description,
            "category_id": category_id,
            "date": date_str,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()


class TestSpendingBreakdown:
    def test_empty_month(self, client, auth_header):
        r = client.get("/spending?month=2025-01", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 0
        assert data["essential_total"] == 0
        assert data["discretionary_total"] == 0
        assert data["categories"] == []

    def test_essential_classification(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Groceries")
        _create_expense(client, auth_header, 50.0, "Weekly groceries", cat_id, "2026-03-10")

        r = client.get("/spending?month=2026-03", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["essential_total"] == 50.0
        assert data["discretionary_total"] == 0
        assert len(data["categories"]) == 1
        assert data["categories"][0]["classification"] == "essential"

    def test_discretionary_classification(self, client, auth_header):
        cat_id = _create_category(client, auth_header, "Entertainment")
        _create_expense(client, auth_header, 30.0, "Movie tickets", cat_id, "2026-03-15")

        r = client.get("/spending?month=2026-03", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["discretionary_total"] >= 30.0
        cats = [c for c in data["categories"] if c["category_name"] == "Entertainment"]
        assert len(cats) == 1
        assert cats[0]["classification"] == "discretionary"

    def test_mixed_spending(self, client, auth_header):
        ess_id = _create_category(client, auth_header, "Rent")
        disc_id = _create_category(client, auth_header, "Dining out")
        _create_expense(client, auth_header, 1000.0, "Monthly rent", ess_id, "2026-04-01")
        _create_expense(client, auth_header, 200.0, "Restaurant", disc_id, "2026-04-05")

        r = client.get("/spending?month=2026-04", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["essential_total"] == 1000.0
        assert data["discretionary_total"] == 200.0
        assert data["total"] == 1200.0
        assert abs(data["essential_pct"] - 83.3) < 0.2
        assert abs(data["discretionary_pct"] - 16.7) < 0.2

    def test_invalid_month_format(self, client, auth_header):
        r = client.get("/spending?month=2026", headers=auth_header)
        assert r.status_code == 400

        r = client.get("/spending?month=abc-de", headers=auth_header)
        assert r.status_code == 400

    def test_uncategorized_defaults_discretionary(self, client, auth_header):
        _create_expense(client, auth_header, 25.0, "Random purchase", None, "2026-05-10")

        r = client.get("/spending?month=2026-05", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        cats = [c for c in data["categories"] if c["category_name"] == "Uncategorized"]
        assert len(cats) == 1
        assert cats[0]["classification"] == "discretionary"

    def test_sorted_by_amount_desc(self, client, auth_header):
        cat1 = _create_category(client, auth_header, "Insurance")
        cat2 = _create_category(client, auth_header, "Shopping")
        _create_expense(client, auth_header, 100.0, "Health insurance", cat1, "2026-06-01")
        _create_expense(client, auth_header, 500.0, "Clothes", cat2, "2026-06-05")

        r = client.get("/spending?month=2026-06", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        amounts = [c["amount"] for c in data["categories"]]
        assert amounts == sorted(amounts, reverse=True)
