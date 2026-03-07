"""Tests for shared household budgeting feature (#134)."""

import pytest


@pytest.fixture()
def auth_header2(client):
    """Register and login a second user for multi-user tests."""
    email = "user2@example.com"
    password = "password456"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (200, 201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


class TestHouseholdCRUD:
    def test_create_household(self, client, auth_header):
        r = client.post(
            "/api/households", json={"name": "Smith Family"}, headers=auth_header
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Smith Family"
        assert "id" in data

    def test_create_household_no_name(self, client, auth_header):
        r = client.post("/api/households", json={"name": ""}, headers=auth_header)
        assert r.status_code == 400

    def test_list_households(self, client, auth_header):
        client.post(
            "/api/households", json={"name": "Household A"}, headers=auth_header
        )
        client.post(
            "/api/households", json={"name": "Household B"}, headers=auth_header
        )
        r = client.get("/api/households", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) >= 2

    def test_get_household(self, client, auth_header):
        r = client.post(
            "/api/households", json={"name": "Test HH"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        r = client.get(f"/api/households/{hid}", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["name"] == "Test HH"
        assert len(data["members"]) == 1
        assert data["members"][0]["role"] == "ADMIN"

    def test_update_household(self, client, auth_header):
        r = client.post(
            "/api/households", json={"name": "Old Name"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        r = client.patch(
            f"/api/households/{hid}", json={"name": "New Name"}, headers=auth_header
        )
        assert r.status_code == 200
        assert r.get_json()["name"] == "New Name"

    def test_delete_household(self, client, auth_header):
        r = client.post(
            "/api/households", json={"name": "Delete Me"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        r = client.delete(f"/api/households/{hid}", headers=auth_header)
        assert r.status_code == 204


class TestMemberManagement:
    def test_add_member(self, client, auth_header, auth_header2):
        r = client.post(
            "/api/households", json={"name": "Shared HH"}, headers=auth_header
        )
        hid = r.get_json()["id"]

        r = client.post(
            f"/api/households/{hid}/members",
            json={"email": "user2@example.com", "role": "MEMBER"},
            headers=auth_header,
        )
        assert r.status_code == 201

        # User2 should now see this household
        r = client.get("/api/households", headers=auth_header2)
        assert any(h["id"] == hid for h in r.get_json())

    def test_add_duplicate_member(self, client, auth_header, auth_header2):
        r = client.post(
            "/api/households", json={"name": "Dup Test"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        client.post(
            f"/api/households/{hid}/members",
            json={"email": "user2@example.com"},
            headers=auth_header,
        )
        r = client.post(
            f"/api/households/{hid}/members",
            json={"email": "user2@example.com"},
            headers=auth_header,
        )
        assert r.status_code == 409

    def test_non_admin_cannot_add_member(self, client, auth_header, auth_header2):
        r = client.post(
            "/api/households", json={"name": "Admin Only"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        client.post(
            f"/api/households/{hid}/members",
            json={"email": "user2@example.com", "role": "MEMBER"},
            headers=auth_header,
        )
        # User2 (MEMBER) tries to add — should fail
        r = client.post(
            f"/api/households/{hid}/members",
            json={"email": "nonexist@test.com"},
            headers=auth_header2,
        )
        assert r.status_code == 403

    def test_remove_member(self, client, auth_header, auth_header2):
        r = client.post(
            "/api/households", json={"name": "Remove Test"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        r = client.post(
            f"/api/households/{hid}/members",
            json={"email": "user2@example.com"},
            headers=auth_header,
        )
        uid = r.get_json()["user_id"]

        r = client.delete(
            f"/api/households/{hid}/members/{uid}", headers=auth_header
        )
        assert r.status_code == 204

    def test_update_member_role(self, client, auth_header, auth_header2):
        r = client.post(
            "/api/households", json={"name": "Role Test"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        r = client.post(
            f"/api/households/{hid}/members",
            json={"email": "user2@example.com", "role": "MEMBER"},
            headers=auth_header,
        )
        uid = r.get_json()["user_id"]

        r = client.patch(
            f"/api/households/{hid}/members/{uid}",
            json={"role": "VIEWER"},
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["role"] == "VIEWER"


class TestSharedExpenses:
    def test_view_household_expenses(self, client, auth_header, auth_header2):
        # Create household and add user2
        r = client.post(
            "/api/households", json={"name": "Expense HH"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        client.post(
            f"/api/households/{hid}/members",
            json={"email": "user2@example.com"},
            headers=auth_header,
        )

        # Both users add expenses
        client.post(
            "/expenses",
            json={"amount": 100, "notes": "Groceries"},
            headers=auth_header,
        )
        client.post(
            "/expenses",
            json={"amount": 50, "notes": "Gas"},
            headers=auth_header2,
        )

        # Both should see all household expenses
        r = client.get(f"/api/households/{hid}/expenses", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] >= 2

    def test_non_member_cannot_view_expenses(self, client, auth_header, auth_header2):
        r = client.post(
            "/api/households", json={"name": "Private HH"}, headers=auth_header
        )
        hid = r.get_json()["id"]

        r = client.get(f"/api/households/{hid}/expenses", headers=auth_header2)
        assert r.status_code == 403


class TestHouseholdBudgets:
    def test_create_budget(self, client, auth_header):
        r = client.post(
            "/api/households", json={"name": "Budget HH"}, headers=auth_header
        )
        hid = r.get_json()["id"]

        r = client.post(
            f"/api/households/{hid}/budgets",
            json={"category": "Groceries", "monthly_limit": 500},
            headers=auth_header,
        )
        assert r.status_code == 201
        assert r.get_json()["category"] == "Groceries"

    def test_list_budgets(self, client, auth_header):
        r = client.post(
            "/api/households", json={"name": "Budget List"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        client.post(
            f"/api/households/{hid}/budgets",
            json={"category": "Food", "monthly_limit": 300},
            headers=auth_header,
        )
        client.post(
            f"/api/households/{hid}/budgets",
            json={"category": "Utilities", "monthly_limit": 200},
            headers=auth_header,
        )

        r = client.get(f"/api/households/{hid}/budgets", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) >= 2

    def test_delete_budget(self, client, auth_header):
        r = client.post(
            "/api/households", json={"name": "Del Budget"}, headers=auth_header
        )
        hid = r.get_json()["id"]
        r = client.post(
            f"/api/households/{hid}/budgets",
            json={"category": "Rent", "monthly_limit": 1000},
            headers=auth_header,
        )
        bid = r.get_json()["id"]

        r = client.delete(
            f"/api/households/{hid}/budgets/{bid}", headers=auth_header
        )
        assert r.status_code == 204


class TestHouseholdSummary:
    def test_summary(self, client, auth_header):
        r = client.post(
            "/api/households", json={"name": "Summary HH"}, headers=auth_header
        )
        hid = r.get_json()["id"]

        # Add budget
        client.post(
            f"/api/households/{hid}/budgets",
            json={"category": "Total", "monthly_limit": 1000},
            headers=auth_header,
        )

        # Add expense
        client.post(
            "/expenses",
            json={"amount": 250, "notes": "Shopping"},
            headers=auth_header,
        )

        r = client.get(f"/api/households/{hid}/summary", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "total_spent" in data
        assert "budget_total" in data
        assert "member_breakdown" in data
