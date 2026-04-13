from datetime import date


def test_digital_twin_requires_auth(client):
    r = client.post("/digital-twin/create")
    assert r.status_code in (401, 422)

    r = client.get("/digital-twin/snapshots")
    assert r.status_code in (401, 422)

    r = client.post("/digital-twin/simulate", json={"snapshot_id": 1})
    assert r.status_code in (401, 422)


def test_create_snapshot(client, auth_header):
    r = client.post("/digital-twin/create", headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert "total_expenses" in data
    assert "total_income" in data
    assert "total_bills" in data
    assert "net_worth" in data
    assert "snapshot_id" in data


def test_list_snapshots(client, auth_header):
    client.post("/digital-twin/create", headers=auth_header)
    client.post("/digital-twin/create", headers=auth_header)

    r = client.get("/digital-twin/snapshots", headers=auth_header)
    assert r.status_code == 200
    snapshots = r.get_json()
    assert len(snapshots) >= 2
    assert all("snapshot_id" in s for s in snapshots)


def test_simulate(client, auth_header):
    # Seed some data
    client.post(
        "/expenses",
        json={
            "amount": 1000,
            "description": "Salary",
            "date": date.today().isoformat(),
            "expense_type": "INCOME",
        },
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={
            "amount": 200,
            "description": "Groceries",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth_header,
    )

    r = client.post("/digital-twin/create", headers=auth_header)
    assert r.status_code == 201
    snapshot_id = r.get_json()["snapshot_id"]

    r = client.post(
        "/digital-twin/simulate",
        json={
            "snapshot_id": snapshot_id,
            "adjustments": {"income_change": 500, "expense_change": -100},
        },
        headers=auth_header,
    )
    assert r.status_code == 200
    result = r.get_json()
    assert result["total_income"] == 1500
    assert result["total_expenses"] == 100
    assert result["net_worth"] == 1400
