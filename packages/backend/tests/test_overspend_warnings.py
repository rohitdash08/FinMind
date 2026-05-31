def _create_category(client, auth_header):
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    return r.get_json()[0]["id"]


def test_set_and_get_budget(client, auth_header):
    cat_id = _create_category(client, auth_header)
    r = client.post(
        "/insights/overspend/budgets",
        json={"category_id": cat_id, "monthly_limit": 500},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["monthly_limit"] == 500.0

    r = client.get("/insights/overspend/budgets", headers=auth_header)
    budgets = r.get_json()
    assert len(budgets) == 1
    assert budgets[0]["category_id"] == cat_id


def test_delete_budget(client, auth_header):
    cat_id = _create_category(client, auth_header)
    r = client.post(
        "/insights/overspend/budgets",
        json={"category_id": cat_id, "monthly_limit": 300},
        headers=auth_header,
    )
    budget_id = r.get_json()["id"]

    r = client.delete(f"/insights/overspend/budgets/{budget_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/insights/overspend/budgets", headers=auth_header)
    assert len(r.get_json()) == 0


def test_warnings_ok(client, auth_header):
    cat_id = _create_category(client, auth_header)
    client.post(
        "/insights/overspend/budgets",
        json={"category_id": cat_id, "monthly_limit": 1000},
        headers=auth_header,
    )

    r = client.get("/insights/overspend/warnings", headers=auth_header)
    assert r.status_code == 200
    warnings = r.get_json()
    assert len(warnings) == 1
    assert warnings[0]["level"] == "ok"
