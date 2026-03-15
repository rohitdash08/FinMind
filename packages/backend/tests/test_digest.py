from datetime import date, timedelta


def _current_week_str():
    today = date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _seed_expense(
    client,
    auth_header,
    amount,
    description,
    spent_at,
    expense_type="EXPENSE",
    category_id=None,
):
    payload = {
        "amount": amount,
        "description": description,
        "date": spent_at.isoformat(),
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def test_digest_empty_week(client, auth_header):
    r = client.get("/digest/weekly?week=2020-W01", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spent"] == 0
    assert data["total_income"] == 0
    assert data["category_breakdown"] == []
    assert data["week_over_week_change"] == 0.0
    assert isinstance(data["trends"], list)
    assert isinstance(data["insights"], list)


def test_digest_populated_week(client, auth_header):
    today = date.today()
    iso = today.isocalendar()
    monday = date.fromisocalendar(iso[0], iso[1], 1)

    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    food_id = r.get_json()["id"]

    _seed_expense(client, auth_header, 500, "Groceries", monday, category_id=food_id)
    _seed_expense(
        client,
        auth_header,
        200,
        "Dining out",
        monday + timedelta(days=1),
        category_id=food_id,
    )
    _seed_expense(client, auth_header, 1000, "Salary", monday, expense_type="INCOME")

    week = f"{iso[0]}-W{iso[1]:02d}"
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_spent"] == 700
    assert data["total_income"] == 1000
    assert len(data["category_breakdown"]) >= 1
    assert data["category_breakdown"][0]["category_name"] == "Food"
    assert isinstance(data["trends"], list)
    assert len(data["trends"]) > 0


def test_digest_week_over_week_comparison(client, auth_header):
    today = date.today()
    iso = today.isocalendar()
    monday = date.fromisocalendar(iso[0], iso[1], 1)
    prev_monday = monday - timedelta(days=7)

    _seed_expense(client, auth_header, 100, "Prev week item", prev_monday)
    _seed_expense(client, auth_header, 300, "This week item", monday)

    week = f"{iso[0]}-W{iso[1]:02d}"
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["week_over_week_change"] == 200.0


def test_digest_requires_auth(client):
    r = client.get("/digest/weekly")
    assert r.status_code in (401, 422)


def test_digest_invalid_week_format(client, auth_header):
    r = client.get("/digest/weekly?week=invalid", headers=auth_header)
    assert r.status_code == 400
    assert "invalid week" in r.get_json()["error"]


def test_digest_defaults_to_current_week(client, auth_header):
    r = client.get("/digest/weekly", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["week"] == _current_week_str()
    assert "period" in data
    assert "start" in data["period"]
    assert "end" in data["period"]


def test_digest_insights_overspend(client, auth_header):
    today = date.today()
    iso = today.isocalendar()
    monday = date.fromisocalendar(iso[0], iso[1], 1)

    _seed_expense(client, auth_header, 500, "Big purchase", monday)
    _seed_expense(
        client, auth_header, 100, "Small income", monday, expense_type="INCOME"
    )

    week = f"{iso[0]}-W{iso[1]:02d}"
    r = client.get(f"/digest/weekly?week={week}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert any("more than you earned" in i for i in data["insights"])
