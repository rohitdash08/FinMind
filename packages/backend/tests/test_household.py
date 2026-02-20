"""Tests for shared household budgeting feature."""

import pytest


@pytest.fixture()
def second_auth_header(client):
    """Register and login a second user."""
    email = "user2@example.com"
    password = "password456"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


class TestHouseholdCreation:
    def test_create_household(self, client, auth_header):
        r = client.post("/household", json={"name": "Test Home"}, headers=auth_header)
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Test Home"
        assert "invite_code" in data

    def test_create_household_no_name(self, client, auth_header):
        r = client.post("/household", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_create_household_duplicate(self, client, auth_header):
        client.post("/household", json={"name": "Home"}, headers=auth_header)
        r = client.post("/household", json={"name": "Home 2"}, headers=auth_header)
        assert r.status_code == 409


class TestHouseholdGet:
    def test_get_household(self, client, auth_header):
        client.post("/household", json={"name": "Home"}, headers=auth_header)
        r = client.get("/household", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["name"] == "Home"

    def test_get_household_not_member(self, client, auth_header, second_auth_header):
        r = client.get("/household", headers=second_auth_header)
        assert r.status_code == 404


class TestHouseholdInvite:
    def test_invite_returns_code(self, client, auth_header):
        client.post("/household", json={"name": "Home"}, headers=auth_header)
        r = client.post("/household/invite", headers=auth_header)
        assert r.status_code == 200
        assert "invite_code" in r.get_json()

    def test_invite_non_owner_forbidden(self, client, auth_header, second_auth_header):
        resp = client.post("/household", json={"name": "Home"}, headers=auth_header)
        code = resp.get_json()["invite_code"]
        client.post(f"/household/join/{code}", headers=second_auth_header)
        r = client.post("/household/invite", headers=second_auth_header)
        assert r.status_code == 403


class TestHouseholdJoin:
    def test_join_household(self, client, auth_header, second_auth_header):
        resp = client.post("/household", json={"name": "Home"}, headers=auth_header)
        code = resp.get_json()["invite_code"]
        r = client.post(f"/household/join/{code}", headers=second_auth_header)
        assert r.status_code == 200

    def test_join_invalid_code(self, client, second_auth_header):
        r = client.post("/household/join/badcode", headers=second_auth_header)
        assert r.status_code == 404

    def test_join_already_in_household(self, client, auth_header):
        resp = client.post("/household", json={"name": "Home"}, headers=auth_header)
        code = resp.get_json()["invite_code"]
        r = client.post(f"/household/join/{code}", headers=auth_header)
        assert r.status_code == 409


class TestHouseholdMembers:
    def test_list_members(self, client, auth_header, second_auth_header):
        resp = client.post("/household", json={"name": "Home"}, headers=auth_header)
        code = resp.get_json()["invite_code"]
        client.post(f"/household/join/{code}", headers=second_auth_header)
        r = client.get("/household/members", headers=auth_header)
        assert r.status_code == 200
        members = r.get_json()
        assert len(members) == 2
        roles = {m["role"] for m in members}
        assert "OWNER" in roles
        assert "MEMBER" in roles


class TestHouseholdExpenses:
    def test_shared_expenses(self, client, auth_header, second_auth_header):
        # Create household and join
        resp = client.post("/household", json={"name": "Home"}, headers=auth_header)
        household = resp.get_json()
        code = household["invite_code"]
        client.post(f"/household/join/{code}", headers=second_auth_header)

        # Create expense with household_id
        r = client.post("/expenses", json={
            "amount": 50,
            "description": "Groceries",
            "household_id": household["id"],
        }, headers=auth_header)
        assert r.status_code == 201

        # Both users can see household expenses
        r = client.get("/household/expenses", headers=auth_header)
        assert r.status_code == 200
        expenses = r.get_json()
        assert len(expenses) == 1
        assert expenses[0]["description"] == "Groceries"

        r2 = client.get("/household/expenses", headers=second_auth_header)
        assert r2.status_code == 200
        assert len(r2.get_json()) == 1

    def test_expense_without_household(self, client, auth_header):
        r = client.post("/expenses", json={
            "amount": 25,
            "description": "Personal lunch",
        }, headers=auth_header)
        assert r.status_code == 201

    def test_expense_wrong_household(self, client, second_auth_header):
        """Non-member cannot tag expense to a household."""
        # second user is not in any household, try to use household_id=999
        r = client.post("/expenses", json={
            "amount": 10,
            "description": "Test",
            "household_id": 999,
        }, headers=second_auth_header)
        assert r.status_code == 403
