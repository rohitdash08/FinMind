"""Tests for merchant & payee alias management endpoints."""
import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _create_merchant(client, headers, canonical_name, aliases=None):
    body = {"canonical_name": canonical_name}
    if aliases:
        body["aliases"] = aliases
    r = client.post("/merchants", json=body, headers=headers)
    return r


def _add_expense(client, headers, notes):
    r = client.post(
        "/expenses",
        json={"amount": 50, "notes": notes, "expense_type": "EXPENSE"},
        headers=headers,
    )
    return r


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_list_merchants_requires_auth(client):
    r = client.get("/merchants")
    assert r.status_code == 401


def test_create_merchant_minimal(client, auth_header):
    r = _create_merchant(client, auth_header, "Starbucks")
    assert r.status_code == 201
    data = r.get_json()
    assert data["canonical_name"] == "Starbucks"
    assert data["aliases"] == []
    assert "id" in data


def test_create_merchant_with_aliases(client, auth_header):
    r = _create_merchant(client, auth_header, "Amazon", aliases=["AMZN", "Amazon.com"])
    assert r.status_code == 201
    data = r.get_json()
    alias_strs = [a["alias"] for a in data["aliases"]]
    assert "AMZN" in alias_strs
    assert "Amazon.com" in alias_strs


def test_create_merchant_missing_name(client, auth_header):
    r = client.post("/merchants", json={}, headers=auth_header)
    assert r.status_code == 400


def test_create_merchant_duplicate(client, auth_header):
    _create_merchant(client, auth_header, "Netflix")
    r = _create_merchant(client, auth_header, "Netflix")
    assert r.status_code == 409


def test_list_merchants(client, auth_header):
    _create_merchant(client, auth_header, "Uber")
    _create_merchant(client, auth_header, "Lyft")
    r = client.get("/merchants", headers=auth_header)
    assert r.status_code == 200
    names = [m["canonical_name"] for m in r.get_json()]
    assert "Uber" in names
    assert "Lyft" in names


def test_list_merchants_filter(client, auth_header):
    _create_merchant(client, auth_header, "Spotify")
    _create_merchant(client, auth_header, "Apple Music")
    r = client.get("/merchants?q=spot", headers=auth_header)
    assert r.status_code == 200
    names = [m["canonical_name"] for m in r.get_json()]
    assert "Spotify" in names
    assert "Apple Music" not in names


def test_get_merchant(client, auth_header):
    cr = _create_merchant(client, auth_header, "Google")
    mid = cr.get_json()["id"]
    r = client.get(f"/merchants/{mid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["canonical_name"] == "Google"


def test_get_merchant_not_found(client, auth_header):
    r = client.get("/merchants/99999", headers=auth_header)
    assert r.status_code == 404


def test_update_merchant(client, auth_header):
    cr = _create_merchant(client, auth_header, "Gogle")
    mid = cr.get_json()["id"]
    r = client.patch(f"/merchants/{mid}", json={"canonical_name": "Google"}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["canonical_name"] == "Google"


def test_delete_merchant(client, auth_header):
    cr = _create_merchant(client, auth_header, "ToDelete")
    mid = cr.get_json()["id"]
    r = client.delete(f"/merchants/{mid}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["deleted"] is True
    r2 = client.get(f"/merchants/{mid}", headers=auth_header)
    assert r2.status_code == 404


def test_add_alias(client, auth_header):
    cr = _create_merchant(client, auth_header, "Walmart")
    mid = cr.get_json()["id"]
    r = client.post(f"/merchants/{mid}/aliases", json={"alias": "WMT"}, headers=auth_header)
    assert r.status_code == 201
    alias_strs = [a["alias"] for a in r.get_json()["aliases"]]
    assert "WMT" in alias_strs


def test_add_alias_duplicate(client, auth_header):
    cr = _create_merchant(client, auth_header, "Target")
    mid = cr.get_json()["id"]
    client.post(f"/merchants/{mid}/aliases", json={"alias": "TGT"}, headers=auth_header)
    r = client.post(f"/merchants/{mid}/aliases", json={"alias": "TGT"}, headers=auth_header)
    assert r.status_code == 409


def test_remove_alias(client, auth_header):
    cr = _create_merchant(client, auth_header, "Costco", aliases=["COST"])
    mid = cr.get_json()["id"]
    alias_id = cr.get_json()["aliases"][0]["id"]
    r = client.delete(f"/merchants/{mid}/aliases/{alias_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["aliases"] == []


def test_merge_merchants(client, auth_header):
    t = _create_merchant(client, auth_header, "McDonald's", aliases=["Mickey D's"])
    s = _create_merchant(client, auth_header, "McDonalds", aliases=["MCD"])
    target_id = t.get_json()["id"]
    source_id = s.get_json()["id"]
    r = client.post(
        "/merchants/merge",
        json={"target_id": target_id, "source_id": source_id},
        headers=auth_header,
    )
    assert r.status_code == 200
    merged = r.get_json()
    assert merged["id"] == target_id
    alias_strs = [a["alias"] for a in merged["aliases"]]
    assert "MCD" in alias_strs
    assert "McDonalds" in alias_strs  # source canonical become alias
    # Source should be gone
    r2 = client.get(f"/merchants/{source_id}", headers=auth_header)
    assert r2.status_code == 404


def test_merge_same_id_error(client, auth_header):
    cr = _create_merchant(client, auth_header, "Tesla")
    mid = cr.get_json()["id"]
    r = client.post(
        "/merchants/merge",
        json={"target_id": mid, "source_id": mid},
        headers=auth_header,
    )
    assert r.status_code == 400


def test_suggest_merchants(client, auth_header):
    _add_expense(client, auth_header, "Whole Foods Market")
    _add_expense(client, auth_header, "Whole Foods Online")
    _add_expense(client, auth_header, "Amazon Fresh")
    r = client.get("/merchants/suggest?q=whole", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "suggestions" in data
    assert any("Whole" in s for s in data["suggestions"])


def test_suggest_merchants_no_query(client, auth_header):
    _add_expense(client, auth_header, "Test Payee")
    r = client.get("/merchants/suggest", headers=auth_header)
    assert r.status_code == 200
    assert "suggestions" in r.get_json()


import pytest
