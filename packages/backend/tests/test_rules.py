"""Tests for auto-tag rules CRUD and auto-tagging on expense creation."""


def _create_category(client, auth_header, name="Groceries"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    cats = r.get_json()
    return next(c["id"] for c in cats if c["name"] == name)


def _make_rule(client, auth_header, name, conditions, cat_id, priority=0):
    r = client.post(
        "/rules",
        json={
            "name": name,
            "conditions": conditions,
            "target_category_id": cat_id,
            "priority": priority,
        },
        headers=auth_header,
    )
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# ── CRUD ──────────────────────────────────────────────────────────────


def test_rules_crud(client, auth_header):
    cat_id = _create_category(client, auth_header, "Food")

    # list empty
    r = client.get("/rules", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # create
    rule = _make_rule(
        client,
        auth_header,
        "Tag groceries",
        [{"type": "keyword_match", "value": "grocery"}],
        cat_id,
    )
    assert rule["name"] == "Tag groceries"
    assert rule["target_category_id"] == cat_id
    assert rule["active"] is True

    # list
    r = client.get("/rules", headers=auth_header)
    assert len(r.get_json()) == 1

    # update
    r = client.patch(
        f"/rules/{rule['id']}",
        json={"name": "Tag food", "priority": 5},
        headers=auth_header,
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Tag food"
    assert updated["priority"] == 5

    # delete
    r = client.delete(f"/rules/{rule['id']}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/rules", headers=auth_header)
    assert r.get_json() == []


def test_create_rule_validation(client, auth_header):
    cat_id = _create_category(client, auth_header, "Transport")

    # missing name
    r = client.post(
        "/rules",
        json={
            "conditions": [{"type": "keyword_match", "value": "uber"}],
            "target_category_id": cat_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 400

    # empty conditions
    r = client.post(
        "/rules",
        json={"name": "Bad", "conditions": [], "target_category_id": cat_id},
        headers=auth_header,
    )
    assert r.status_code == 400

    # invalid condition type
    r = client.post(
        "/rules",
        json={
            "name": "Bad",
            "conditions": [{"type": "invalid_type", "value": "x"}],
            "target_category_id": cat_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 400

    # amount_range min > max
    r = client.post(
        "/rules",
        json={
            "name": "Bad",
            "conditions": [{"type": "amount_range", "min": 100, "max": 10}],
            "target_category_id": cat_id,
        },
        headers=auth_header,
    )
    assert r.status_code == 400

    # missing target_category_id
    r = client.post(
        "/rules",
        json={
            "name": "No cat",
            "conditions": [{"type": "keyword_match", "value": "x"}],
        },
        headers=auth_header,
    )
    assert r.status_code == 400


def test_rule_not_found(client, auth_header):
    r = client.patch("/rules/99999", json={"name": "x"}, headers=auth_header)
    assert r.status_code == 404

    r = client.delete("/rules/99999", headers=auth_header)
    assert r.status_code == 404


# ── Auto-tagging on expense creation ──────────────────────────────────


def test_auto_tag_keyword_match(client, auth_header):
    cat_id = _create_category(client, auth_header, "Coffee")
    _make_rule(
        client,
        auth_header,
        "Coffee rule",
        [{"type": "keyword_match", "value": "starbucks"}],
        cat_id,
    )

    # Create expense without category — should auto-tag
    r = client.post(
        "/expenses",
        json={"amount": 5.50, "description": "Starbucks latte", "date": "2026-02-20"},
        headers=auth_header,
    )
    assert r.status_code == 201
    expense = r.get_json()
    assert expense["category_id"] == cat_id


def test_auto_tag_merchant_match(client, auth_header):
    cat_id = _create_category(client, auth_header, "Rides")
    _make_rule(
        client,
        auth_header,
        "Uber rule",
        [{"type": "merchant_match", "value": "uber"}],
        cat_id,
    )

    r = client.post(
        "/expenses",
        json={"amount": 22.0, "description": "Uber trip downtown", "date": "2026-02-20"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["category_id"] == cat_id


def test_auto_tag_amount_range(client, auth_header):
    cat_id = _create_category(client, auth_header, "Big purchases")
    _make_rule(
        client,
        auth_header,
        "Big spend",
        [{"type": "amount_range", "min": 500, "max": 10000}],
        cat_id,
    )

    # Under range — no match
    r = client.post(
        "/expenses",
        json={"amount": 50, "description": "Small item", "date": "2026-02-20"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["category_id"] is None

    # In range — match
    r = client.post(
        "/expenses",
        json={"amount": 750, "description": "New phone", "date": "2026-02-20"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["category_id"] == cat_id


def test_auto_tag_combined_conditions(client, auth_header):
    cat_id = _create_category(client, auth_header, "Fancy dining")
    _make_rule(
        client,
        auth_header,
        "Expensive restaurant",
        [
            {"type": "keyword_match", "value": "restaurant"},
            {"type": "amount_range", "min": 100},
        ],
        cat_id,
    )

    # Keyword matches but amount too low
    r = client.post(
        "/expenses",
        json={"amount": 25, "description": "Restaurant lunch", "date": "2026-02-20"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["category_id"] is None

    # Both match
    r = client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Restaurant dinner party",
            "date": "2026-02-20",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["category_id"] == cat_id


def test_auto_tag_priority_ordering(client, auth_header):
    cat_food = _create_category(client, auth_header, "Food general")
    cat_fast = _create_category(client, auth_header, "Fast food")

    _make_rule(
        client,
        auth_header,
        "Food generic",
        [{"type": "keyword_match", "value": "mcdonald"}],
        cat_food,
        priority=1,
    )
    _make_rule(
        client,
        auth_header,
        "Fast food specific",
        [{"type": "keyword_match", "value": "mcdonald"}],
        cat_fast,
        priority=10,
    )

    r = client.post(
        "/expenses",
        json={"amount": 12, "description": "McDonald's burger", "date": "2026-02-20"},
        headers=auth_header,
    )
    assert r.status_code == 201
    # Higher priority rule wins
    assert r.get_json()["category_id"] == cat_fast


def test_auto_tag_skipped_when_category_provided(client, auth_header):
    cat_coffee = _create_category(client, auth_header, "Coffee2")
    cat_other = _create_category(client, auth_header, "Other")
    _make_rule(
        client,
        auth_header,
        "Coffee rule 2",
        [{"type": "keyword_match", "value": "starbucks"}],
        cat_coffee,
    )

    # Explicitly provide a different category — auto-tag should NOT override
    r = client.post(
        "/expenses",
        json={
            "amount": 5.50,
            "description": "Starbucks latte",
            "date": "2026-02-20",
            "category_id": cat_other,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["category_id"] == cat_other


def test_auto_tag_inactive_rule_ignored(client, auth_header):
    cat_id = _create_category(client, auth_header, "Inactive cat")
    rule = _make_rule(
        client,
        auth_header,
        "Inactive rule",
        [{"type": "keyword_match", "value": "netflix"}],
        cat_id,
    )
    # Deactivate
    r = client.patch(
        f"/rules/{rule['id']}",
        json={"active": False},
        headers=auth_header,
    )
    assert r.status_code == 200

    r = client.post(
        "/expenses",
        json={"amount": 15, "description": "Netflix subscription", "date": "2026-02-20"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["category_id"] is None
