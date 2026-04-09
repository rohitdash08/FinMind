import pytest
from http import HTTPStatus
from app.models import PayeeMerchantAlias, Category
from app.extensions import db


def test_payee_merchant_alias_crud_flow(client, auth_header):
    # Initially empty
    r = client.get("/payee-merchant-aliases", headers=auth_header)
    assert r.status_code == HTTPStatus.OK
    assert r.get_json() == []

    # Create a category first for testing category_id linking
    r = client.post("/categories", json={"name": "Groceries"}, headers=auth_header)
    assert r.status_code == HTTPStatus.CREATED
    category_id = r.get_json()["id"]

    # Create alias 1 (with category)
    alias_data_1 = {
        "raw_name": "Starbucks Coffee",
        "canonical_name": "Starbucks",
        "category_id": category_id,
    }
    r = client.post(
        "/payee-merchant-aliases", json=alias_data_1, headers=auth_header
    )
    assert r.status_code == HTTPStatus.CREATED
    alias_1 = r.get_json()
    assert alias_1["raw_name"] == alias_data_1["raw_name"]
    assert alias_1["canonical_name"] == alias_data_1["canonical_name"]
    assert alias_1["category_id"] == alias_data_1["category_id"]

    # Create alias 2 (without category)
    alias_data_2 = {
        "raw_name": "Walmart Supercenter",
        "canonical_name": "Walmart",
    }
    r = client.post(
        "/payee-merchant-aliases", json=alias_data_2, headers=auth_header
    )
    assert r.status_code == HTTPStatus.CREATED
    alias_2 = r.get_json()
    assert alias_2["raw_name"] == alias_data_2["raw_name"]
    assert alias_2["canonical_name"] == alias_data_2["canonical_name"]
    assert alias_2["category_id"] is None

    # List should have 2 aliases
    r = client.get("/payee-merchant-aliases", headers=auth_header)
    assert r.status_code == HTTPStatus.OK
    items = r.get_json()
    assert len(items) == 2
    assert any(item["id"] == alias_1["id"] for item in items)
    assert any(item["id"] == alias_2["id"] for item in items)

    # Attempt to create duplicate raw_name (case-insensitive)
    duplicate_data = {
        "raw_name": "starbucks coffee",  # same as alias_1, but different case
        "canonical_name": "Different Starbucks",
    }
    r = client.post(
        "/payee-merchant-aliases", json=duplicate_data, headers=auth_header
    )
    assert r.status_code == HTTPStatus.CONFLICT

    # Get single alias
    r = client.get(f"/payee-merchant-aliases/{alias_1['id']}", headers=auth_header)
    assert r.status_code == HTTPStatus.OK
    retrieved_alias = r.get_json()
    assert retrieved_alias["id"] == alias_1["id"]
    assert retrieved_alias["raw_name"] == alias_1["raw_name"]

    # Update alias 1's canonical_name and category
    update_data = {"canonical_name": "Starbucks Inc.", "category_id": None}
    r = client.patch(
        f"/payee-merchant-aliases/{alias_1['id']}",
        json=update_data,
        headers=auth_header,
    )
    assert r.status_code == HTTPStatus.OK
    updated_alias_1 = r.get_json()
    assert updated_alias_1["canonical_name"] == update_data["canonical_name"]
    assert updated_alias_1["category_id"] is None
    assert updated_alias_1["raw_name"] == alias_1["raw_name"]  # raw_name should not change

    # Update alias 2's category to an existing one
    r = client.post("/categories", json={"name": "Restaurants"}, headers=auth_header)
    assert r.status_code == HTTPStatus.CREATED
    new_category_id = r.get_json()["id"]

    update_data_cat = {"category_id": new_category_id}
    r = client.patch(
        f"/payee-merchant-aliases/{alias_2['id']}",
        json=update_data_cat,
        headers=auth_header,
    )
    assert r.status_code == HTTPStatus.OK
    updated_alias_2 = r.get_json()
    assert updated_alias_2["category_id"] == new_category_id

    # Attempt to update with a non-existent category
    update_data_bad_cat = {"category_id": 99999}
    r = client.patch(
        f"/payee-merchant-aliases/{alias_2['id']}",
        json=update_data_bad_cat,
        headers=auth_header,
    )
    assert r.status_code == HTTPStatus.BAD_REQUEST

    # Delete alias 1
    r = client.delete(f"/payee-merchant-aliases/{alias_1['id']}", headers=auth_header)
    assert r.status_code == HTTPStatus.OK
    assert r.get_json()["message"] == "Alias deleted"

    # List should have 1 alias now
    r = client.get("/payee-merchant-aliases", headers=auth_header)
    assert r.status_code == HTTPStatus.OK
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == alias_2["id"]

    # Attempt to get deleted alias
    r = client.get(f"/payee-merchant-aliases/{alias_1['id']}", headers=auth_header)
    assert r.status_code == HTTPStatus.NOT_FOUND

    # Delete alias 2
    r = client.delete(f"/payee-merchant-aliases/{alias_2['id']}", headers=auth_header)
    assert r.status_code == HTTPStatus.OK

    # List should be empty again
    r = client.get("/payee-merchant-aliases", headers=auth_header)
    assert r.status_code == HTTPStatus.OK
    assert r.get_json() == []


def test_payee_merchant_alias_auth_and_ownership(client, auth_header):
    # Create alias as user 1
    alias_data = {
        "raw_name": "User1Alias",
        "canonical_name": "User1 Canonical",
    }
    r = client.post(
        "/payee-merchant-aliases", json=alias_data, headers=auth_header
    )
    assert r.status_code == HTTPStatus.CREATED
    alias_id_user1 = r.get_json()["id"]

    # Login as a different user
    email = "test2@example.com"
    password = "password123"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == HTTPStatus.OK
    auth_header_user2 = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    # Attempt to list aliases as user 2 - should be empty
    r = client.get("/payee-merchant-aliases", headers=auth_header_user2)
    assert r.status_code == HTTPStatus.OK
    assert r.get_json() == []

    # Attempt to get user 1's alias as user 2 - should be 404
    r = client.get(
        f"/payee-merchant-aliases/{alias_id_user1}", headers=auth_header_user2
    )
    assert r.status_code == HTTPStatus.NOT_FOUND

    # Attempt to update user 1's alias as user 2 - should be 404
    update_data = {"canonical_name": "Malicious Update"}
    r = client.patch(
        f"/payee-merchant-aliases/{alias_id_user1}",
        json=update_data,
        headers=auth_header_user2,
    )
    assert r.status_code == HTTPStatus.NOT_FOUND

    # Attempt to delete user 1's alias as user 2 - should be 404
    r = client.delete(
        f"/payee-merchant-aliases/{alias_id_user1}", headers=auth_header_user2
    )
    assert r.status_code == HTTPStatus.NOT_FOUND

    # Create an alias for user 2
    alias_data_user2 = {
        "raw_name": "User2Alias",
        "canonical_name": "User2 Canonical",
    }
    r = client.post(
        "/payee-merchant-aliases", json=alias_data_user2, headers=auth_header_user2
    )
    assert r.status_code == HTTPStatus.CREATED
    alias_id_user2 = r.get_json()["id"]

    # Delete user 2's alias (cleanup)
    r = client.delete(
        f"/payee-merchant-aliases/{alias_id_user2}", headers=auth_header_user2
    )
    assert r.status_code == HTTPStatus.OK

