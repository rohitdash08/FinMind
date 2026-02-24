"""Tests for Budget CRUD and overspend warning system."""


def _create_category(client, auth_header, name="TestCat"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    cats = r.get_json()
    return next(c["id"] for c in cats if c["name"] == name)


def _create_expense(client, auth_header, amount, category_id, spent_at="2026-02-15"):
    return client.post(
        "/expenses",
        json={
            "amount": amount,
            "category_id": category_id,
            "description": "test expense",
            "date": spent_at,
        },
        headers=auth_header,
    )


def test_budget_crud(client, auth_header):
    cat_id = _create_category(client, auth_header, "Food")

    # Create budget
    r = client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 500, "period": "MONTHLY"},
        headers=auth_header,
    )
    assert r.status_code == 201
    budget = r.get_json()
    assert budget["amount"] == 500.0
    assert budget["period"] == "MONTHLY"
    assert budget["category_id"] == cat_id
    budget_id = budget["id"]

    # List budgets
    r = client.get("/budgets", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 1

    # Update budget
    r = client.patch(
        f"/budgets/{budget_id}",
        json={"amount": 600},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["amount"] == 600.0

    # Delete budget
    r = client.delete(f"/budgets/{budget_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/budgets", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 0


def test_budget_duplicate_rejected(client, auth_header):
    cat_id = _create_category(client, auth_header, "Transport")
    r = client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 200, "period": "MONTHLY"},
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 300, "period": "MONTHLY"},
        headers=auth_header,
    )
    assert r.status_code == 409


def test_budget_validation(client, auth_header):
    # Missing category_id
    r = client.post(
        "/budgets",
        json={"amount": 100, "period": "MONTHLY"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid amount
    r = client.post(
        "/budgets",
        json={"category_id": 999, "amount": -10, "period": "MONTHLY"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Invalid period
    cat_id = _create_category(client, auth_header, "Misc")
    r = client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 100, "period": "DAILY"},
        headers=auth_header,
    )
    assert r.status_code == 400

    # Non-existent category
    r = client.post(
        "/budgets",
        json={"category_id": 99999, "amount": 100, "period": "MONTHLY"},
        headers=auth_header,
    )
    assert r.status_code == 404


def test_budget_not_found(client, auth_header):
    r = client.patch("/budgets/99999", json={"amount": 100}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/budgets/99999", headers=auth_header)
    assert r.status_code == 404


def test_warnings_no_budgets(client, auth_header):
    r = client.get("/budgets/warnings", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_warning_at_80_percent(client, auth_header):
    cat_id = _create_category(client, auth_header, "Groceries")
    client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 100, "period": "MONTHLY"},
        headers=auth_header,
    )
    # Spend 85 (>80%)
    _create_expense(client, auth_header, 85, cat_id, "2026-02-15")

    r = client.get("/budgets/warnings", headers=auth_header)
    assert r.status_code == 200
    warnings = r.get_json()
    assert len(warnings) == 1
    assert warnings[0]["level"] == "warning"
    assert warnings[0]["category_name"] == "Groceries"
    assert warnings[0]["percentage"] >= 80


def test_warning_at_100_percent(client, auth_header):
    cat_id = _create_category(client, auth_header, "Entertainment")
    client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 100, "period": "MONTHLY"},
        headers=auth_header,
    )
    _create_expense(client, auth_header, 110, cat_id, "2026-02-15")

    r = client.get("/budgets/warnings", headers=auth_header)
    assert r.status_code == 200
    warnings = r.get_json()
    assert len(warnings) == 1
    assert warnings[0]["level"] == "exceeded"
    assert warnings[0]["percentage"] >= 100


def test_no_warning_under_threshold(client, auth_header):
    cat_id = _create_category(client, auth_header, "Utilities")
    client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 100, "period": "MONTHLY"},
        headers=auth_header,
    )
    _create_expense(client, auth_header, 50, cat_id, "2026-02-15")

    r = client.get("/budgets/warnings", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) == 0


def test_expense_create_returns_budget_warning(client, auth_header):
    cat_id = _create_category(client, auth_header, "Shopping")
    client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 100, "period": "MONTHLY"},
        headers=auth_header,
    )
    # First expense pushes past 80%
    r = _create_expense(client, auth_header, 90, cat_id, "2026-02-15")
    assert r.status_code == 201
    body = r.get_json()
    assert "budget_warnings" in body
    assert len(body["budget_warnings"]) == 1
    assert body["budget_warnings"][0]["level"] in ("warning", "exceeded")


def test_expense_create_no_warning_when_under(client, auth_header):
    cat_id = _create_category(client, auth_header, "Health")
    client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 1000, "period": "MONTHLY"},
        headers=auth_header,
    )
    r = _create_expense(client, auth_header, 10, cat_id, "2026-02-15")
    assert r.status_code == 201
    body = r.get_json()
    assert "budget_warnings" not in body


def test_weekly_budget_warning(client, auth_header):
    cat_id = _create_category(client, auth_header, "Snacks")
    client.post(
        "/budgets",
        json={"category_id": cat_id, "amount": 50, "period": "WEEKLY"},
        headers=auth_header,
    )
    # Spend 45 (90% of 50)
    _create_expense(client, auth_header, 45, cat_id, "2026-02-16")

    r = client.get("/budgets/warnings", headers=auth_header)
    assert r.status_code == 200
    warnings = r.get_json()
    assert len(warnings) == 1
    assert warnings[0]["period"] == "WEEKLY"
