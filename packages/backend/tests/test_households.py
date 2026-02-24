"""Tests for shared household budgeting."""
import pytest


def _register(client, email, password="secret123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)


def _login(client, email, password="secret123"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.get_json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestHouseholdCRUD:
    def test_create_household(self, client):
        _register(client, "owner@test.com")
        token = _login(client, "owner@test.com")
        r = client.post(
            "/households",
            json={"name": "Home", "currency": "USD", "monthly_budget": 3000},
            headers=_auth(token),
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Home"
        assert data["role"] == "OWNER"
        assert data["monthly_budget"] in ("3000", "3000.00")

    def test_create_household_requires_name(self, client):
        _register(client, "owner2@test.com")
        token = _login(client, "owner2@test.com")
        r = client.post("/households", json={}, headers=_auth(token))
        assert r.status_code == 400

    def test_list_households(self, client):
        _register(client, "list@test.com")
        token = _login(client, "list@test.com")
        client.post("/households", json={"name": "H1"}, headers=_auth(token))
        client.post("/households", json={"name": "H2"}, headers=_auth(token))
        r = client.get("/households", headers=_auth(token))
        assert r.status_code == 200
        assert len(r.get_json()["households"]) == 2

    def test_get_household_detail(self, client):
        _register(client, "detail@test.com")
        token = _login(client, "detail@test.com")
        r = client.post(
            "/households",
            json={"name": "Detail House", "monthly_budget": 5000},
            headers=_auth(token),
        )
        hid = r.get_json()["id"]
        r = client.get(f"/households/{hid}", headers=_auth(token))
        assert r.status_code == 200
        data = r.get_json()
        assert data["name"] == "Detail House"
        assert len(data["members"]) == 1

    def test_update_household_owner_only(self, client):
        _register(client, "upd_owner@test.com")
        token = _login(client, "upd_owner@test.com")
        r = client.post("/households", json={"name": "Old"}, headers=_auth(token))
        hid = r.get_json()["id"]
        r = client.patch(
            f"/households/{hid}",
            json={"name": "New", "monthly_budget": 1000},
            headers=_auth(token),
        )
        assert r.status_code == 200
        assert r.get_json()["name"] == "New"


class TestHouseholdInvitations:
    def test_invite_and_accept(self, client):
        _register(client, "inviter@test.com")
        _register(client, "invitee@test.com")
        owner_token = _login(client, "inviter@test.com")
        member_token = _login(client, "invitee@test.com")

        # Create household
        r = client.post(
            "/households", json={"name": "Family"}, headers=_auth(owner_token)
        )
        hid = r.get_json()["id"]

        # Invite
        r = client.post(
            f"/households/{hid}/invite",
            json={"email": "invitee@test.com"},
            headers=_auth(owner_token),
        )
        assert r.status_code == 201
        invite_id = r.get_json()["id"]

        # Check pending invites
        r = client.get("/households/invites", headers=_auth(member_token))
        assert r.status_code == 200
        invites = r.get_json()["invites"]
        assert len(invites) == 1

        # Accept
        r = client.post(
            f"/households/invites/{invite_id}/accept",
            headers=_auth(member_token),
        )
        assert r.status_code == 200

        # Verify membership
        r = client.get(f"/households/{hid}", headers=_auth(member_token))
        assert r.status_code == 200
        assert len(r.get_json()["members"]) == 2

    def test_decline_invite(self, client):
        _register(client, "decl_owner@test.com")
        _register(client, "decl_user@test.com")
        owner_token = _login(client, "decl_owner@test.com")
        user_token = _login(client, "decl_user@test.com")

        r = client.post(
            "/households", json={"name": "Decline"}, headers=_auth(owner_token)
        )
        hid = r.get_json()["id"]
        r = client.post(
            f"/households/{hid}/invite",
            json={"email": "decl_user@test.com"},
            headers=_auth(owner_token),
        )
        invite_id = r.get_json()["id"]

        r = client.post(
            f"/households/invites/{invite_id}/decline",
            headers=_auth(user_token),
        )
        assert r.status_code == 200

    def test_duplicate_invite_rejected(self, client):
        _register(client, "dup_owner@test.com")
        token = _login(client, "dup_owner@test.com")
        r = client.post(
            "/households", json={"name": "Dup"}, headers=_auth(token)
        )
        hid = r.get_json()["id"]
        client.post(
            f"/households/{hid}/invite",
            json={"email": "someone@test.com"},
            headers=_auth(token),
        )
        r = client.post(
            f"/households/{hid}/invite",
            json={"email": "someone@test.com"},
            headers=_auth(token),
        )
        assert r.status_code == 409


class TestHouseholdExpenses:
    def test_add_and_list_expenses(self, client):
        _register(client, "exp@test.com")
        token = _login(client, "exp@test.com")
        r = client.post(
            "/households",
            json={"name": "Budget House", "monthly_budget": 2000},
            headers=_auth(token),
        )
        hid = r.get_json()["id"]

        # Add expenses
        client.post(
            f"/households/{hid}/expenses",
            json={"amount": 50.00, "notes": "Groceries"},
            headers=_auth(token),
        )
        client.post(
            f"/households/{hid}/expenses",
            json={"amount": 120.00, "notes": "Electric bill"},
            headers=_auth(token),
        )

        # List
        r = client.get(f"/households/{hid}/expenses", headers=_auth(token))
        assert r.status_code == 200
        expenses = r.get_json()["expenses"]
        assert len(expenses) == 2

    def test_expense_requires_valid_amount(self, client):
        _register(client, "amt@test.com")
        token = _login(client, "amt@test.com")
        r = client.post(
            "/households", json={"name": "Amt"}, headers=_auth(token)
        )
        hid = r.get_json()["id"]
        r = client.post(
            f"/households/{hid}/expenses",
            json={"amount": -10},
            headers=_auth(token),
        )
        assert r.status_code == 400

    def test_non_member_cannot_add_expense(self, client):
        _register(client, "mem_a@test.com")
        _register(client, "mem_b@test.com")
        token_a = _login(client, "mem_a@test.com")
        token_b = _login(client, "mem_b@test.com")

        r = client.post(
            "/households", json={"name": "Private"}, headers=_auth(token_a)
        )
        hid = r.get_json()["id"]

        r = client.post(
            f"/households/{hid}/expenses",
            json={"amount": 10, "notes": "Sneaky"},
            headers=_auth(token_b),
        )
        assert r.status_code == 403


class TestHouseholdSummary:
    def test_monthly_summary(self, client):
        _register(client, "sum@test.com")
        token = _login(client, "sum@test.com")
        r = client.post(
            "/households",
            json={"name": "Summary", "monthly_budget": 1000},
            headers=_auth(token),
        )
        hid = r.get_json()["id"]

        client.post(
            f"/households/{hid}/expenses",
            json={"amount": 200},
            headers=_auth(token),
        )

        r = client.get(f"/households/{hid}/summary", headers=_auth(token))
        assert r.status_code == 200
        data = r.get_json()
        assert float(data["total_spent"]) == 200.0
        assert float(data["remaining"]) == 800.0


class TestLeaveAndRemove:
    def test_member_can_leave(self, client):
        _register(client, "leave_own@test.com")
        _register(client, "leave_mem@test.com")
        own_token = _login(client, "leave_own@test.com")
        mem_token = _login(client, "leave_mem@test.com")

        r = client.post(
            "/households", json={"name": "Leave"}, headers=_auth(own_token)
        )
        hid = r.get_json()["id"]

        # Invite and accept
        r = client.post(
            f"/households/{hid}/invite",
            json={"email": "leave_mem@test.com"},
            headers=_auth(own_token),
        )
        inv_id = r.get_json()["id"]
        client.post(
            f"/households/invites/{inv_id}/accept", headers=_auth(mem_token)
        )

        # Member leaves
        r = client.post(f"/households/{hid}/leave", headers=_auth(mem_token))
        assert r.status_code == 200

    def test_owner_cannot_leave(self, client):
        _register(client, "own_stay@test.com")
        token = _login(client, "own_stay@test.com")
        r = client.post(
            "/households", json={"name": "Stay"}, headers=_auth(token)
        )
        hid = r.get_json()["id"]
        r = client.post(f"/households/{hid}/leave", headers=_auth(token))
        assert r.status_code == 400
