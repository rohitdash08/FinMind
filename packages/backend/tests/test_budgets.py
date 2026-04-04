from datetime import date


def _create_category(client, auth_header, name="Food"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    cats = r.get_json()
    return next(c["id"] for c in cats if c["name"] == name)


def _add_expense(client, auth_header, amount, category_id, dt="2026-04-10"):
    r = client.post("/expenses", json={
        "amount": amount, "category_id": category_id,
        "description": "test", "date": dt,
    }, headers=auth_header)
    assert r.status_code == 201


def test_create_budget_limit(client, auth_header):
    cat_id = _create_category(client, auth_header)
    r = client.post("/budgets", json={
        "category_id": cat_id, "monthly_limit": 500, "month": "2026-04",
    }, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert data["monthly_limit"] == 500
    assert data["category_id"] == cat_id


def test_budget_warnings_status_levels(client, auth_header):
    cat_0 = _create_category(client, auth_header, "Zero")
    cat_80 = _create_category(client, auth_header, "Eighty")
    cat_95 = _create_category(client, auth_header, "NinetyFive")
    cat_110 = _create_category(client, auth_header, "Over")

    month = "2026-04"
    for cat_id in [cat_0, cat_80, cat_95, cat_110]:
        client.post("/budgets", json={
            "category_id": cat_id, "monthly_limit": 100, "month": month,
        }, headers=auth_header)

    _add_expense(client, auth_header, 80, cat_80)
    _add_expense(client, auth_header, 95, cat_95)
    _add_expense(client, auth_header, 110, cat_110)

    r = client.get(f"/budgets/warnings?month={month}", headers=auth_header)
    assert r.status_code == 200
    items = {w["category_name"]: w for w in r.get_json()}

    assert items["Zero"]["status"] == "ok"
    assert items["Zero"]["pct_used"] == 0

    assert items["Eighty"]["status"] == "warning"
    assert items["Eighty"]["pct_used"] == 80.0

    assert items["NinetyFive"]["status"] == "critical"
    assert items["NinetyFive"]["pct_used"] == 95.0

    assert items["Over"]["status"] == "over"
    assert items["Over"]["pct_used"] == 110.0
