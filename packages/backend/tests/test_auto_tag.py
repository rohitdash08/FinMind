def test_create_and_list_rules(client, auth_header):
    r = client.post(
        "/auto-tag/rules",
        json={"name": "Food", "rule_type": "KEYWORD", "match_value": "grocery,restaurant"},
        headers=auth_header,
    )
    assert r.status_code == 201
    rule_id = r.get_json()["id"]

    r = client.get("/auto-tag/rules", headers=auth_header)
    assert r.status_code == 200
    rules = r.get_json()
    ids = [x["id"] for x in rules]
    assert rule_id in ids


def test_update_rule(client, auth_header):
    r = client.post(
        "/auto-tag/rules",
        json={"name": "Transport", "rule_type": "KEYWORD", "match_value": "uber,lyft"},
        headers=auth_header,
    )
    rule_id = r.get_json()["id"]

    r = client.patch(
        f"/auto-tag/rules/{rule_id}",
        json={"name": "Travel", "priority": 5},
        headers=auth_header,
    )
    assert r.status_code == 200


def test_delete_rule(client, auth_header):
    r = client.post(
        "/auto-tag/rules",
        json={"name": "Test", "rule_type": "CATEGORY", "match_value": "test"},
        headers=auth_header,
    )
    rule_id = r.get_json()["id"]

    r = client.delete(f"/auto-tag/rules/{rule_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/auto-tag/rules", headers=auth_header)
    assert rule_id not in [x["id"] for x in r.get_json()]


def test_apply_rules_endpoint(client, auth_header):
    r = client.post("/auto-tag/apply", headers=auth_header)
    assert r.status_code == 200
    assert "applied" in r.get_json()


def test_learn_from_correction(client, auth_header):
    r = client.post(
        "/expenses",
        json={"amount": 10, "description": "test expense", "expense_type": "EXPENSE"},
        headers=auth_header,
    )
    expense_id = r.get_json()["id"]

    r = client.post(
        "/categories",
        json={"name": "Learning Cat"},
        headers=auth_header,
    )
    cat_id = r.get_json()["id"]

    r = client.post(
        "/auto-tag/learn",
        json={"expense_id": expense_id, "category_id": cat_id},
        headers=auth_header,
    )
    assert r.status_code == 200
