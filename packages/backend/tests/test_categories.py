def test_categories_crud_flow(client, auth_header):
    # Initially empty
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 201
    c1 = r.get_json()
    assert c1["name"] == "Food"

    # Duplicate create should 409
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code == 409

    # List should have 1
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1

    # Update
    r = client.patch(
        f"/categories/{c1['id']}", json={"name": "Groceries"}, headers=auth_header
    )
    assert r.status_code == 200
    updated = r.get_json()
    assert updated["name"] == "Groceries"

    # Delete
    r = client.delete(f"/categories/{c1['id']}", headers=auth_header)
    assert r.status_code == 200

    # List should be empty again
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []
