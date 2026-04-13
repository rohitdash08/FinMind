"""Tests for rule-based auto-tagging."""


def _create_rule(client, auth_header, name="Groceries Rule", field="notes", operator="contains", value="grocery", category_id=None, tag=None):
    payload = {"name": name, "field": field, "operator": operator, "value": value}
    if category_id:
        payload["category_id"] = category_id
    if tag:
        payload["tag"] = tag
    r = client.post("/tagging/rules", json=payload, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _add_expense(client, auth_header, amount, desc):
    r = client.post("/expenses", json={"amount": amount, "description": desc, "expense_type": "EXPENSE"}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _create_category(client, auth_header, name):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


# 1. Auth required
def test_tagging_requires_auth(client):
    r = client.get("/tagging/rules")
    assert r.status_code in (401, 422)


# 2. Create rule
def test_create_rule(client, auth_header):
    rule = _create_rule(client, auth_header, "Coffee", "notes", "contains", "coffee")
    assert rule["name"] == "Coffee"
    assert rule["field"] == "notes"
    assert rule["operator"] == "contains"
    assert rule["active"] is True


# 3. List rules
def test_list_rules(client, auth_header):
    _create_rule(client, auth_header, "Rule A", "notes", "contains", "food")
    _create_rule(client, auth_header, "Rule B", "amount", "gt", "100")
    r = client.get("/tagging/rules", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) >= 2


# 4. Delete rule
def test_delete_rule(client, auth_header):
    rule = _create_rule(client, auth_header, "ToDelete", "notes", "contains", "x")
    r = client.delete(f"/tagging/rules/{rule['id']}", headers=auth_header)
    assert r.status_code == 200


# 5. Invalid field returns 400
def test_invalid_field(client, auth_header):
    r = client.post("/tagging/rules", json={"name": "Bad", "field": "invalid", "operator": "contains", "value": "x"}, headers=auth_header)
    assert r.status_code == 400


# 6. Apply rules categorizes expenses
def test_apply_rules(client, auth_header):
    cat = _create_category(client, auth_header, "Food")
    _create_rule(client, auth_header, "Grocery auto", "notes", "contains", "grocery", category_id=cat["id"])
    _add_expense(client, auth_header, 50, "Weekly grocery shopping")
    _add_expense(client, auth_header, 30, "Gas station")
    r = client.post("/tagging/rules/apply", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["matched"] >= 1


# 7. Test rules (dry run)
def test_dry_run(client, auth_header):
    _create_rule(client, auth_header, "Big spend", "amount", "gt", "100")
    _add_expense(client, auth_header, 200, "Large purchase")
    _add_expense(client, auth_header, 20, "Small item")
    r = client.post("/tagging/rules/test", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_matches"] >= 1
    assert any(m["expense_amount"] == 200.0 for m in data["matches"])


# 8. Contains operator case-insensitive
def test_contains_case_insensitive(client, auth_header):
    _create_rule(client, auth_header, "Coffee", "notes", "contains", "COFFEE")
    _add_expense(client, auth_header, 5, "Morning coffee run")
    r = client.post("/tagging/rules/test", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["total_matches"] >= 1
