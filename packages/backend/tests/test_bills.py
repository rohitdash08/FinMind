from datetime import date
import uuid


def test_bills_crud_and_mark_paid(client, auth_header):
    # Initially empty
    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create category to link bills to
    r = client.post("/categories", json={"name": "Utilities"}, headers=auth_header)
    assert r.status_code == 201
    category_id = r.get_json()["id"]

    # Create bill with category_id
    payload = {
        "name": "Internet",
        "amount": 49.99,
        "currency": "USD",
        "next_due_date": date.today().isoformat(),
        "cadence": "MONTHLY",
        "channel_email": True,
        "channel_whatsapp": False,
        "category_id": category_id
    }
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code == 201
    bill_data = r.get_json()
    bill_id = bill_data["id"]
    assert bill_data["category_id"] == category_id

    # Get bill
    r = client.get(f"/bills/{bill_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["category_id"] == category_id

    # List has 1
    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert any(b["id"] == bill_id for b in items)

    # Update bill, change category to None
    r = client.patch(f"/bills/{bill_id}", json={"category_id": None}, headers=auth_header)
    assert r.status_code == 200
    updated_bill = r.get_json()
    assert updated_bill["category_id"] is None

    # Update bill, re-assign category
    r = client.patch(f"/bills/{bill_id}", json={"category_id": category_id}, headers=auth_header)
    assert r.status_code == 200
    updated_bill = r.get_json()
    assert updated_bill["category_id"] == category_id

    # Mark paid
    r = client.post(f"/bills/{bill_id}/pay", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "updated"

    # Delete bill
    r = client.delete(f"/bills/{bill_id}", headers=auth_header)
    assert r.status_code == 200

    # List should be empty again
    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Cleanup category
    r = client.delete(f"/categories/{category_id}", headers=auth_header)
    assert r.status_code == 200


def test_bill_create_with_invalid_category_id(client, auth_header):
    invalid_category_id = str(uuid.uuid4())
    payload = {
        "name": "Invalid Category Bill",
        "amount": 10.0,
        "next_due_date": date.today().isoformat(),
        "cadence": "MONTHLY",
        "category_id": invalid_category_id
    }
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code == 404
    assert r.get_json()["message"] == "Category not found."


def test_bill_update_with_invalid_category_id(client, auth_header):
    # Create a bill first
    payload = {
        "name": "Bill to Update",
        "amount": 20.0,
        "next_due_date": date.today().isoformat(),
        "cadence": "MONTHLY",
    }
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code == 201
    bill_id = r.get_json()["id"]

    # Try to update it with an invalid category ID
    invalid_category_id = str(uuid.uuid4())
    r = client.patch(f"/bills/{bill_id}", json={"category_id": invalid_category_id}, headers=auth_header)
    assert r.status_code == 404
    assert r.get_json()["message"] == "Category not found."

    # Clean up
    client.delete(f"/bills/{bill_id}", headers=auth_header)


def test_bill_create_defaults_to_user_preferred_currency(client, auth_header):
    # Ensure preferred currency is set for the user (default from conftest is INR)
    r = client.patch(
        "/auth/me", json={"preferred_currency": "INR"}, headers=auth_header
    )
    assert r.status_code == 200

    payload = {
        "name": "Gas",
        "amount": 30.0,
        "next_due_date": date.today().isoformat(),
        "cadence": "MONTHLY",
    }
    r = client.post("/bills", json=payload, headers=auth_header)
    assert r.status_code == 201
    bill_id = r.get_json()["id"]

    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    created = next((item for item in r.get_json() if item["id"] == bill_id), None)
    assert created is not None
    assert created["currency"] == "INR"

    # Cleanup
    client.delete(f"/bills/{bill_id}", headers=auth_header)
