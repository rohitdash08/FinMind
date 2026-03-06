import pytest


def _register_and_login(client, email, password="password123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


class TestSharedBudgets:
    def test_create_shared_budget(self, client, auth_header):
        r = client.post(
            "/shared-budgets",
            json={"name": "Household", "monthly_limit": 5000, "description": "Family budget"},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["name"] == "Household"
        assert "id" in data

    def test_list_shared_budgets(self, client, auth_header):
        client.post(
            "/shared-budgets",
            json={"name": "Budget A", "monthly_limit": 1000},
            headers=auth_header,
        )
        client.post(
            "/shared-budgets",
            json={"name": "Budget B", "monthly_limit": 2000},
            headers=auth_header,
        )
        r = client.get("/shared-budgets", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) == 2

    def test_add_member_to_budget(self, client, auth_header):
        # Create budget
        r = client.post(
            "/shared-budgets",
            json={"name": "Family", "monthly_limit": 3000},
            headers=auth_header,
        )
        budget_id = r.get_json()["id"]

        # Register second user
        _register_and_login(client, "member@example.com")

        # Add member
        r = client.post(
            f"/shared-budgets/{budget_id}/members",
            json={"email": "member@example.com"},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["role"] == "member"

    def test_remove_member(self, client, auth_header):
        r = client.post(
            "/shared-budgets",
            json={"name": "Family", "monthly_limit": 3000},
            headers=auth_header,
        )
        budget_id = r.get_json()["id"]
        _register_and_login(client, "member2@example.com")
        r = client.post(
            f"/shared-budgets/{budget_id}/members",
            json={"email": "member2@example.com"},
            headers=auth_header,
        )
        member_id = r.get_json()["id"]

        r = client.delete(
            f"/shared-budgets/{budget_id}/members/{member_id}",
            headers=auth_header,
        )
        assert r.status_code == 200
        assert r.get_json()["message"] == "removed"

    def test_add_shared_expense(self, client, auth_header):
        r = client.post(
            "/shared-budgets",
            json={"name": "Groceries", "monthly_limit": 2000},
            headers=auth_header,
        )
        budget_id = r.get_json()["id"]

        r = client.post(
            f"/shared-budgets/{budget_id}/expenses",
            json={"amount": 150.50, "description": "Weekly groceries"},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["amount"] == 150.50
        assert data["description"] == "Weekly groceries"

    def test_budget_summary_calculation(self, client, auth_header):
        r = client.post(
            "/shared-budgets",
            json={"name": "House", "monthly_limit": 5000},
            headers=auth_header,
        )
        budget_id = r.get_json()["id"]

        client.post(
            f"/shared-budgets/{budget_id}/expenses",
            json={"amount": 100, "description": "Expense 1"},
            headers=auth_header,
        )
        client.post(
            f"/shared-budgets/{budget_id}/expenses",
            json={"amount": 250, "description": "Expense 2"},
            headers=auth_header,
        )

        r = client.get(f"/shared-budgets/{budget_id}", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_spent"] == 350.0
        assert data["remaining"] == 4650.0
        assert data["monthly_limit"] == 5000

    def test_non_owner_cannot_delete(self, client, auth_header):
        r = client.post(
            "/shared-budgets",
            json={"name": "Family", "monthly_limit": 3000},
            headers=auth_header,
        )
        budget_id = r.get_json()["id"]

        member_header = _register_and_login(client, "other@example.com")

        # Add member first
        client.post(
            f"/shared-budgets/{budget_id}/members",
            json={"email": "other@example.com"},
            headers=auth_header,
        )

        # Try to delete as member
        r = client.delete(f"/shared-budgets/{budget_id}", headers=member_header)
        assert r.status_code == 403

    def test_requires_auth(self, client):
        r = client.post(
            "/shared-budgets",
            json={"name": "Test", "monthly_limit": 1000},
        )
        assert r.status_code == 401

        r = client.get("/shared-budgets")
        assert r.status_code == 401
