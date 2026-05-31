def _create_category(client, auth_header, name="General"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    cats = r.get_json()
    for c in cats:
        if c["name"] == name:
            return c["id"]
    return cats[0]["id"]


def test_auto_tag_rules_crud(client, auth_header):
    r = client.get("/auto-tag/rules", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    payload = {
        "name": "Coffee tagging",
        "condition_field": "notes",
        "condition_operator": "contains",
        "condition_value": "coffee",
        "priority": 10,
    }
    r = client.post("/auto-tag/rules", json=payload, headers=auth_header)
    assert r.status_code == 201
    rule_id = r.get_json()["id"]

    r = client.get("/auto-tag/rules", headers=auth_header)
    assert r.status_code == 200
    rules = r.get_json()
    assert len(rules) == 1
    assert rules[0]["name"] == "Coffee tagging"

    r = client.put(
        f"/auto-tag/rules/{rule_id}",
        json={"name": "Coffee & Tea tagging"},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.delete(f"/auto-tag/rules/{rule_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/auto-tag/rules", headers=auth_header)
    assert r.get_json() == []


def test_auto_tag_applies_on_expense_create(client, auth_header):
    cat_id = _create_category(client, auth_header, "Beverages")

    r = client.post(
        "/auto-tag/rules",
        json={
            "name": "Coffee rule",
            "condition_field": "notes",
            "condition_operator": "contains",
            "condition_value": "coffee",
            "target_category_id": cat_id,
            "priority": 5,
        },
        headers=auth_header,
    )
    rule_id = r.get_json()["id"]
    assert rule_id

    r = client.post(
        "/expenses",
        json={"amount": 5.0, "description": "Morning coffee", "date": "2026-06-01"},
        headers=auth_header,
    )
    assert r.status_code == 201
    expense = r.get_json()
    assert expense["category_id"] == cat_id


def test_auto_tag_feedback_and_learning(client, auth_header):
    r = client.post(
        "/auto-tag/feedback",
        json={
            "expense_id": 1,
            "old_category_id": 1,
            "new_category_id": 2,
            "rule_id": 1,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get("/auto-tag/learning-suggestions", headers=auth_header)
    assert r.status_code == 200
    suggestions = r.get_json()
    assert isinstance(suggestions, list)
