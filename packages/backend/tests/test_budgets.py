"""Tests for category budget management and overspend early warnings (#117)."""

from datetime import date


MONTH = date.today().strftime("%Y-%m")


# ── helpers ───────────────────────────────────────────────────────────────────

def _create_category(client, auth_header, name="Food"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (200, 201)
    return r.get_json()["id"]


def _create_budget(client, auth_header, category_id, limit=1000, month=None, threshold=80):
    payload = {
        "category_id": category_id,
        "budget_limit": limit,
        "warning_threshold_pct": threshold,
    }
    if month:
        payload["month"] = month
    return client.post("/budgets", json=payload, headers=auth_header)


def _add_expense(client, auth_header, category_id, amount, expense_type="EXPENSE"):
    r = client.post(
        "/expenses",
        json={
            "category_id": category_id,
            "amount": amount,
            "expense_type": expense_type,
            "spent_at": date.today().isoformat(),
        },
        headers=auth_header,
    )
    assert r.status_code in (200, 201)


# ── Budget CRUD ───────────────────────────────────────────────────────────────


def test_list_budgets_empty(client, auth_header):
    r = client.get("/budgets", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_budget(client, auth_header):
    cid = _create_category(client, auth_header)
    r = _create_budget(client, auth_header, category_id=cid, limit=500)
    assert r.status_code == 201
    data = r.get_json()
    assert data["budget_limit"] == 500.0
    assert data["category_id"] == cid
    assert data["warning_threshold_pct"] == 80


def test_create_budget_with_month(client, auth_header):
    cid = _create_category(client, auth_header)
    r = _create_budget(client, auth_header, category_id=cid, month="2025-01")
    assert r.status_code == 201
    assert r.get_json()["month"] == "2025-01"


def test_create_budget_invalid_limit(client, auth_header):
    cid = _create_category(client, auth_header)
    r = _create_budget(client, auth_header, category_id=cid, limit=-100)
    assert r.status_code == 400


def test_create_budget_invalid_category(client, auth_header):
    r = _create_budget(client, auth_header, category_id=99999)
    assert r.status_code == 404


def test_create_budget_missing_category(client, auth_header):
    r = client.post("/budgets", json={"budget_limit": 500}, headers=auth_header)
    assert r.status_code == 400


def test_update_budget(client, auth_header):
    cid = _create_category(client, auth_header)
    bid = _create_budget(client, auth_header, category_id=cid, limit=500).get_json()["id"]
    r = client.patch(f"/budgets/{bid}", json={"budget_limit": 750, "warning_threshold_pct": 90}, headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["budget_limit"] == 750.0
    assert data["warning_threshold_pct"] == 90


def test_delete_budget(client, auth_header):
    cid = _create_category(client, auth_header)
    bid = _create_budget(client, auth_header, category_id=cid).get_json()["id"]
    r = client.delete(f"/budgets/{bid}", headers=auth_header)
    assert r.status_code == 200
    assert client.get("/budgets", headers=auth_header).get_json() == []


# ── Overspend warnings ────────────────────────────────────────────────────────


def test_overspend_no_budgets(client, auth_header):
    r = client.get("/budgets/overspend", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["warnings"] == []
    assert data["summary"]["total"] == 0


def test_overspend_ok_level(client, auth_header):
    """25% spent → OK level."""
    cid = _create_category(client, auth_header, "Transport")
    _create_budget(client, auth_header, category_id=cid, limit=1000, threshold=80)
    _add_expense(client, auth_header, cid, 250)
    r = client.get(f"/budgets/overspend?month={MONTH}", headers=auth_header)
    warnings = r.get_json()["warnings"]
    assert len(warnings) == 1
    assert warnings[0]["warning_level"] == "OK"
    assert warnings[0]["pct_used"] == 25.0


def test_overspend_medium_level(client, auth_header):
    """80% spent with 80% threshold → MEDIUM→HIGH boundary: pct=80 >= threshold(80)."""
    cid = _create_category(client, auth_header, "Shopping")
    _create_budget(client, auth_header, category_id=cid, limit=1000, threshold=80)
    _add_expense(client, auth_header, cid, 800)
    r = client.get(f"/budgets/overspend?month={MONTH}", headers=auth_header)
    w = r.get_json()["warnings"][0]
    # 80% used = exactly at threshold → MEDIUM or higher
    assert w["pct_used"] == 80.0
    assert w["warning_level"] in ("MEDIUM", "HIGH", "CRITICAL")


def test_overspend_critical_level(client, auth_header):
    """Over budget → CRITICAL."""
    cid = _create_category(client, auth_header, "Dining")
    _create_budget(client, auth_header, category_id=cid, limit=500, threshold=80)
    _add_expense(client, auth_header, cid, 600)
    r = client.get(f"/budgets/overspend?month={MONTH}", headers=auth_header)
    w = r.get_json()["warnings"][0]
    assert w["warning_level"] == "CRITICAL"
    assert w["is_over_budget"] is True
    assert w["remaining"] < 0


def test_overspend_only_warnings_filter(client, auth_header):
    """?only_warnings=true should exclude OK categories."""
    cid1 = _create_category(client, auth_header, "Health")
    cid2 = _create_category(client, auth_header, "Utilities")
    _create_budget(client, auth_header, category_id=cid1, limit=500, threshold=80)
    _create_budget(client, auth_header, category_id=cid2, limit=100, threshold=80)
    _add_expense(client, auth_header, cid1, 50)   # 10% → OK
    _add_expense(client, auth_header, cid2, 96)   # 96% → HIGH
    r = client.get(f"/budgets/overspend?month={MONTH}&only_warnings=true", headers=auth_header)
    warnings = r.get_json()["warnings"]
    assert all(w["warning_level"] != "OK" for w in warnings)


def test_overspend_income_not_counted(client, auth_header):
    """INCOME transactions should not count toward spending."""
    cid = _create_category(client, auth_header, "Salary")
    _create_budget(client, auth_header, category_id=cid, limit=1000, threshold=80)
    _add_expense(client, auth_header, cid, 5000, expense_type="INCOME")
    r = client.get(f"/budgets/overspend?month={MONTH}", headers=auth_header)
    w = r.get_json()["warnings"][0]
    assert w["spent"] == 0.0
    assert w["pct_used"] == 0.0


def test_overspend_unauthorized(client):
    r = client.get("/budgets/overspend")
    assert r.status_code == 401
