#!/usr/bin/env python3
import sys

with open('packages/backend/tests/test_dashboard.py', 'r') as f:
    content = f.read()

new_tests = '''

def test_dashboard_summary_with_account_filter(client, auth_header):
    """Dashboard should filter by account_id when provided."""
    # Create two financial accounts
    r = client.post("/accounts", json={"name": "Checking", "type": "BANK"}, headers=auth_header)
    assert r.status_code == 201
    acc1 = r.get_json()["id"]
    r = client.post("/accounts", json={"name": "Credit Card", "type": "CREDIT_CARD"}, headers=auth_header)
    assert r.status_code == 201
    acc2 = r.get_json()["id"]

    # Create expense assigned to account 1
    r = client.post(
        "/expenses",
        json={
            "amount": 100,
            "description": "Expense on Checking",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
            "account_id": acc1,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    # Create expense assigned to account 2
    r = client.post(
        "/expenses",
        json={
            "amount": 50,
            "description": "Expense on Credit Card",
            "date": date.today().isoformat(),
            "expense_type": "EXPENSE",
            "account_id": acc2,
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Dashboard without account_id should include both expenses
    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["monthly_expenses"] == 150.0

    # Dashboard with account_id=acc1 should only show expense for that account
    r = client.get(f"/dashboard/summary?account_id={acc1}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["monthly_expenses"] == 100.0

    # Dashboard with account_id=acc2 should only show expense for that account
    r = client.get(f"/dashboard/summary?account_id={acc2}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["monthly_expenses"] == 50.0


def test_dashboard_summary_invalid_account_id(client, auth_header):
    """Invalid account_id should return 404."""
    r = client.get("/dashboard/summary?account_id=999999", headers=auth_header)
    assert r.status_code == 404
    payload = r.get_json()
    assert "error" in payload
    assert "not found" in payload["error"].lower()


def test_dashboard_summary_account_filter_with_bills(client, auth_header):
    """Upcoming bills should also be filtered by account_id."""
    # Create account
    r = client.post("/accounts", json={"name": "Checking", "type": "BANK"}, headers=auth_header)
    assert r.status_code == 201
    acc = r.get_json()["id"]
    # Create bill assigned to account
    r = client.post(
        "/bills",
        json={
            "name": "Internet Bill",
            "amount": 49.99,
            "next_due_date": (date.today() + timedelta(days=3)).isoformat(),
            "cadence": "MONTHLY",
            "account_id": acc,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    # Create another bill without account (should be excluded when filtering)
    r = client.post(
        "/bills",
        json={
            "name": "Phone Bill",
            "amount": 29.99,
            "next_due_date": (date.today() + timedelta(days=5)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    r = client.get(f"/dashboard/summary?account_id={acc}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["upcoming_bills_count"] == 1
    assert data["upcoming_bills"][0]["name"] == "Internet Bill"
'''

# Append after the last line
content = content.rstrip() + '\n' + new_tests

with open('packages/backend/tests/test_dashboard.py', 'w') as f:
    f.write(content)

print("Tests appended")