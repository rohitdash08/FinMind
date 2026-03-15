"""Tests for smart payee & merchant alias management."""

import pytest
from app.extensions import db
from app.models import Merchant, MerchantAlias, Category


def _create_category(client, name="Food"):
    with client.application.app_context():
        cat = Category(name=name, user_id=1)
        db.session.add(cat)
        db.session.commit()
        return cat.id


def _create_merchant(client, name="Starbucks", category_id=None):
    with client.application.app_context():
        from app.services.smart_payee import create_merchant
        return create_merchant(1, name, category_id=category_id)


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — CRUD
# ═══════════════════════════════════════════════════════════════════


class TestMerchantCRUD:
    def test_create(self, client, auth_header):
        m = _create_merchant(client, "Starbucks")
        assert m["name"] == "Starbucks"
        assert m["normalized_name"] == "starbucks"

    def test_create_duplicate(self, client, auth_header):
        _create_merchant(client, "Starbucks")
        with pytest.raises(ValueError, match="already exists"):
            _create_merchant(client, "Starbucks")

    def test_create_normalizes(self, client, auth_header):
        m = _create_merchant(client, "  Star BUCKS!  ")
        assert m["normalized_name"] == "star bucks"

    def test_get(self, client, auth_header):
        from app.services.smart_payee import get_merchant
        m = _create_merchant(client, "Walmart")
        with client.application.app_context():
            result = get_merchant(1, m["id"])
        assert result["name"] == "Walmart"

    def test_get_not_found(self, client, auth_header):
        from app.services.smart_payee import get_merchant
        with client.application.app_context():
            result = get_merchant(1, 999)
        assert result is None

    def test_list(self, client, auth_header):
        from app.services.smart_payee import list_merchants
        _create_merchant(client, "Alpha")
        _create_merchant(client, "Beta")
        with client.application.app_context():
            result = list_merchants(1)
        assert result["total"] == 2
        assert result["merchants"][0]["name"] == "Alpha"  # sorted by name

    def test_list_search(self, client, auth_header):
        from app.services.smart_payee import list_merchants
        _create_merchant(client, "Starbucks")
        _create_merchant(client, "Walmart")
        with client.application.app_context():
            result = list_merchants(1, search="star")
        assert result["total"] == 1

    def test_update(self, client, auth_header):
        from app.services.smart_payee import update_merchant
        m = _create_merchant(client, "Starbuks")
        with client.application.app_context():
            result = update_merchant(1, m["id"], name="Starbucks")
        assert result["name"] == "Starbucks"

    def test_delete(self, client, auth_header):
        from app.services.smart_payee import delete_merchant, get_merchant
        m = _create_merchant(client, "ToDelete")
        with client.application.app_context():
            assert delete_merchant(1, m["id"]) is True
            assert get_merchant(1, m["id"]) is None


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — Aliases
# ═══════════════════════════════════════════════════════════════════


class TestAliases:
    def test_add_alias(self, client, auth_header):
        from app.services.smart_payee import add_alias
        m = _create_merchant(client, "Starbucks")
        with client.application.app_context():
            a = add_alias(1, m["id"], "SBUX")
        assert a["alias"] == "SBUX"
        assert a["normalized_alias"] == "sbux"

    def test_add_duplicate_alias(self, client, auth_header):
        from app.services.smart_payee import add_alias
        m = _create_merchant(client, "Starbucks")
        with client.application.app_context():
            add_alias(1, m["id"], "SBUX")
            with pytest.raises(ValueError, match="already exists"):
                add_alias(1, m["id"], "SBUX")

    def test_add_conflicting_alias(self, client, auth_header):
        from app.services.smart_payee import add_alias
        _create_merchant(client, "Starbucks")
        m2 = _create_merchant(client, "Walmart")
        with client.application.app_context():
            with pytest.raises(ValueError, match="conflicts"):
                add_alias(1, m2["id"], "Starbucks")

    def test_list_aliases(self, client, auth_header):
        from app.services.smart_payee import add_alias, list_aliases
        m = _create_merchant(client, "Starbucks")
        with client.application.app_context():
            add_alias(1, m["id"], "SBUX")
            add_alias(1, m["id"], "Starbux")
            result = list_aliases(1, m["id"])
        assert len(result) == 2

    def test_remove_alias(self, client, auth_header):
        from app.services.smart_payee import add_alias, remove_alias, list_aliases
        m = _create_merchant(client, "Starbucks")
        with client.application.app_context():
            a = add_alias(1, m["id"], "SBUX")
            assert remove_alias(1, m["id"], a["id"]) is True
            assert list_aliases(1, m["id"]) == []


# ═══════════════════════════════════════════════════════════════════
# Service unit tests — Merge & Matching
# ═══════════════════════════════════════════════════════════════════


class TestMergeAndMatching:
    def test_merge(self, client, auth_header):
        from app.services.smart_payee import merge_merchants, get_merchant

        m1 = _create_merchant(client, "Starbucks")
        m2 = _create_merchant(client, "SBUX Coffee")

        with client.application.app_context():
            result = merge_merchants(1, m1["id"], [m2["id"]])

        assert result["merged_count"] == 1
        assert result["aliases_added"] >= 1  # Source name becomes alias

        with client.application.app_context():
            target = get_merchant(1, m1["id"])
            assert any(a["alias"] == "SBUX Coffee" for a in target["aliases"])
            assert get_merchant(1, m2["id"]) is None  # Source deleted

    def test_match_by_name(self, client, auth_header):
        from app.services.smart_payee import match_merchant

        _create_merchant(client, "Starbucks")
        with client.application.app_context():
            result = match_merchant(1, "Starbucks")
        assert result is not None
        assert result["name"] == "Starbucks"

    def test_match_by_alias(self, client, auth_header):
        from app.services.smart_payee import match_merchant, add_alias

        m = _create_merchant(client, "Starbucks")
        with client.application.app_context():
            add_alias(1, m["id"], "SBUX")
            result = match_merchant(1, "SBUX")
        assert result is not None
        assert result["name"] == "Starbucks"

    def test_match_partial(self, client, auth_header):
        from app.services.smart_payee import match_merchant

        _create_merchant(client, "Starbucks Coffee")
        with client.application.app_context():
            result = match_merchant(1, "starbucks")
        assert result is not None

    def test_match_not_found(self, client, auth_header):
        from app.services.smart_payee import match_merchant

        with client.application.app_context():
            result = match_merchant(1, "NonExistent")
        assert result is None

    def test_suggest_duplicates(self, client, auth_header):
        from app.services.smart_payee import suggest_duplicates

        _create_merchant(client, "Starbucks")
        _create_merchant(client, "Starbucks Coffee")

        with client.application.app_context():
            duplicates = suggest_duplicates(1)

        assert len(duplicates) >= 1
        assert duplicates[0]["similarity"] == "substring_match"


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestMerchantRoutes:
    # ── CRUD ──
    def test_create_route(self, client, auth_header):
        r = client.post("/merchants", headers=auth_header, json={"name": "Starbucks"})
        assert r.status_code == 201
        assert r.get_json()["name"] == "Starbucks"

    def test_create_missing_name(self, client, auth_header):
        r = client.post("/merchants", headers=auth_header, json={})
        assert r.status_code == 400

    def test_list_route(self, client, auth_header):
        client.post("/merchants", headers=auth_header, json={"name": "Alpha"})
        client.post("/merchants", headers=auth_header, json={"name": "Beta"})
        r = client.get("/merchants", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] == 2

    def test_get_route(self, client, auth_header):
        r = client.post("/merchants", headers=auth_header, json={"name": "Test"})
        mid = r.get_json()["id"]
        r = client.get(f"/merchants/{mid}", headers=auth_header)
        assert r.status_code == 200

    def test_get_not_found(self, client, auth_header):
        r = client.get("/merchants/999", headers=auth_header)
        assert r.status_code == 404

    def test_update_route(self, client, auth_header):
        r = client.post("/merchants", headers=auth_header, json={"name": "Old"})
        mid = r.get_json()["id"]
        r = client.put(f"/merchants/{mid}", headers=auth_header, json={"name": "New"})
        assert r.status_code == 200
        assert r.get_json()["name"] == "New"

    def test_delete_route(self, client, auth_header):
        r = client.post("/merchants", headers=auth_header, json={"name": "Del"})
        mid = r.get_json()["id"]
        r = client.delete(f"/merchants/{mid}", headers=auth_header)
        assert r.status_code == 200

    def test_unauthorized(self, client):
        r = client.get("/merchants")
        assert r.status_code == 401

    # ── Aliases ──
    def test_add_alias_route(self, client, auth_header):
        r = client.post("/merchants", headers=auth_header, json={"name": "Star"})
        mid = r.get_json()["id"]
        r = client.post(f"/merchants/{mid}/aliases", headers=auth_header, json={"alias": "SB"})
        assert r.status_code == 201

    def test_list_aliases_route(self, client, auth_header):
        r = client.post("/merchants", headers=auth_header, json={"name": "Star"})
        mid = r.get_json()["id"]
        client.post(f"/merchants/{mid}/aliases", headers=auth_header, json={"alias": "SB"})
        r = client.get(f"/merchants/{mid}/aliases", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()["aliases"]) == 1

    def test_remove_alias_route(self, client, auth_header):
        r = client.post("/merchants", headers=auth_header, json={"name": "Star"})
        mid = r.get_json()["id"]
        r = client.post(f"/merchants/{mid}/aliases", headers=auth_header, json={"alias": "SB"})
        aid = r.get_json()["id"]
        r = client.delete(f"/merchants/{mid}/aliases/{aid}", headers=auth_header)
        assert r.status_code == 200

    # ── Merge & Matching ──
    def test_merge_route(self, client, auth_header):
        r1 = client.post("/merchants", headers=auth_header, json={"name": "Star"})
        r2 = client.post("/merchants", headers=auth_header, json={"name": "SBux"})
        r = client.post("/merchants/merge", headers=auth_header, json={
            "target_id": r1.get_json()["id"],
            "source_ids": [r2.get_json()["id"]],
        })
        assert r.status_code == 200
        assert r.get_json()["merged_count"] == 1

    def test_match_route(self, client, auth_header):
        client.post("/merchants", headers=auth_header, json={"name": "Starbucks"})
        r = client.get("/merchants/match?name=Starbucks", headers=auth_header)
        assert r.status_code == 200

    def test_match_not_found(self, client, auth_header):
        r = client.get("/merchants/match?name=XYZ", headers=auth_header)
        assert r.status_code == 404

    def test_duplicates_route(self, client, auth_header):
        client.post("/merchants", headers=auth_header, json={"name": "Starbucks"})
        client.post("/merchants", headers=auth_header, json={"name": "Starbucks Plus"})
        r = client.get("/merchants/duplicates", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] >= 1
