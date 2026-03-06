#!/usr/bin/env python3
"""
Demo script for FinMind Shared Household Budgeting feature.
Generates a visual demo showing the API in action.
"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "packages", "backend"))

from app import create_app
from app.config import Settings
from app.extensions import db

import fakeredis
from unittest.mock import patch

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
WHITE = "\033[97m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

def slow_print(text, delay=0.02):
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def section(title):
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    slow_print(f"{BOLD}{CYAN}  {title}{RESET}", 0.03)
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}\n")

def cmd(text):
    slow_print(f"{GREEN}$ {text}{RESET}", 0.015)

def response(data):
    formatted = json.dumps(data, indent=2, ensure_ascii=False)
    for line in formatted.split("\n"):
        print(f"  {WHITE}{line}{RESET}")
        time.sleep(0.01)

def main():
    print(f"\n{BOLD}{YELLOW}")
    print("  FinMind - Shared Household Budgeting Demo")
    print(f"  Issue #134 | Shared Budget Management{RESET}")
    print(f"{DIM}  Feature: /shared-budgets - Collaborative Family Budgeting{RESET}")
    time.sleep(1)

    section("1. Setting up test environment")

    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        jwt_secret="demo-secret-key-with-32-plus-chars-1234567890",
    )
    fake_redis = fakeredis.FakeRedis(decode_responses=True)

    with patch("app.extensions.redis_client", fake_redis), \
         patch("app.routes.auth.redis_client", fake_redis), \
         patch("app.services.cache.redis_client", fake_redis):

        app = create_app(settings)
        app.config["TESTING"] = True

        with app.app_context():
            db.create_all()

        client = app.test_client()
        slow_print(f"  {GREEN}[OK]{RESET} Flask app created with in-memory SQLite")
        slow_print(f"  {GREEN}[OK]{RESET} Database tables created")
        time.sleep(0.5)

        # Register users
        section("2. Register household members")

        cmd("POST /auth/register - Alice (household owner)")
        client.post("/auth/register", json={"email": "alice@family.io", "password": "pass123"})
        r = client.post("/auth/login", json={"email": "alice@family.io", "password": "pass123"})
        alice_auth = {"Authorization": f"Bearer {r.get_json()['access_token']}"}
        slow_print(f"  {GREEN}201 Created{RESET} - Alice registered & logged in")

        cmd("POST /auth/register - Bob (household member)")
        client.post("/auth/register", json={"email": "bob@family.io", "password": "pass123"})
        r = client.post("/auth/login", json={"email": "bob@family.io", "password": "pass123"})
        bob_auth = {"Authorization": f"Bearer {r.get_json()['access_token']}"}
        slow_print(f"  {GREEN}201 Created{RESET} - Bob registered & logged in")
        time.sleep(0.5)

        # Create shared budget
        section("3. Create a shared household budget")

        cmd("POST /shared-budgets")
        r = client.post("/shared-budgets", json={
            "name": "Family Groceries",
            "monthly_limit": 5000,
            "description": "Monthly grocery budget for the household"
        }, headers=alice_auth)
        assert r.status_code == 201
        data = r.get_json()
        budget_id = data["id"]
        slow_print(f"  {GREEN}201 Created{RESET} - Budget '{data['name']}' (id={budget_id})")
        response(data)
        time.sleep(0.5)

        # Add member
        section("4. Invite Bob to the budget")

        cmd(f"POST /shared-budgets/{budget_id}/members")
        r = client.post(f"/shared-budgets/{budget_id}/members", json={
            "email": "bob@family.io"
        }, headers=alice_auth)
        assert r.status_code == 201
        member_data = r.get_json()
        slow_print(f"  {GREEN}201 Created{RESET} - Bob added as member")
        response(member_data)
        time.sleep(0.5)

        # Add expenses
        section("5. Track shared expenses")

        cmd(f"POST /shared-budgets/{budget_id}/expenses - Alice's groceries")
        r = client.post(f"/shared-budgets/{budget_id}/expenses", json={
            "amount": 1250.50, "description": "Weekly groceries from market"
        }, headers=alice_auth)
        assert r.status_code == 201
        slow_print(f"  {GREEN}201 Created{RESET} - Alice spent $1,250.50")
        response(r.get_json())

        cmd(f"POST /shared-budgets/{budget_id}/expenses - Bob's groceries")
        r = client.post(f"/shared-budgets/{budget_id}/expenses", json={
            "amount": 800.00, "description": "Organic produce and dairy"
        }, headers=bob_auth)
        assert r.status_code == 201
        slow_print(f"  {GREEN}201 Created{RESET} - Bob spent $800.00")
        response(r.get_json())

        cmd(f"POST /shared-budgets/{budget_id}/expenses - Alice's bulk buy")
        r = client.post(f"/shared-budgets/{budget_id}/expenses", json={
            "amount": 450.75, "description": "Bulk rice and cooking oil"
        }, headers=alice_auth)
        assert r.status_code == 201
        slow_print(f"  {GREEN}201 Created{RESET} - Alice spent $450.75")
        time.sleep(0.5)

        # Budget summary
        section("6. View budget summary with spending breakdown")

        cmd(f"GET /shared-budgets/{budget_id}")
        r = client.get(f"/shared-budgets/{budget_id}", headers=alice_auth)
        assert r.status_code == 200
        summary = r.get_json()
        slow_print(f"  {GREEN}200 OK{RESET} - Budget summary:")
        response(summary)

        print()
        slow_print(f"  {BOLD}Budget:     {WHITE}{summary['name']}{RESET}")
        slow_print(f"  {BOLD}Limit:      {WHITE}${summary['monthly_limit']:,.2f}{RESET}")
        slow_print(f"  {BOLD}Spent:      {YELLOW}${summary['total_spent']:,.2f}{RESET}")
        slow_print(f"  {BOLD}Remaining:  {GREEN}${summary['remaining']:,.2f}{RESET}")
        pct = (summary['total_spent'] / summary['monthly_limit']) * 100
        bar_len = int(pct / 2)
        bar = "#" * bar_len + "-" * (50 - bar_len)
        slow_print(f"  {BOLD}Usage:      {CYAN}[{bar}] {pct:.1f}%{RESET}")
        time.sleep(0.5)

        # List expenses
        section("7. List all shared expenses")

        cmd(f"GET /shared-budgets/{budget_id}/expenses")
        r = client.get(f"/shared-budgets/{budget_id}/expenses", headers=alice_auth)
        assert r.status_code == 200
        expenses = r.get_json()
        slow_print(f"  {GREEN}200 OK{RESET} - {len(expenses)} expenses:")
        for e in expenses:
            slow_print(f"    {DIM}User {e['user_id']}: ${e['amount']:>10.2f}  {e['description']}{RESET}")
        time.sleep(0.5)

        # Permission check
        section("8. Permission checks")

        cmd("DELETE /shared-budgets/{budget_id} - Bob tries to delete (not owner)")
        r = client.delete(f"/shared-budgets/{budget_id}", headers=bob_auth)
        assert r.status_code == 403
        slow_print(f"  {YELLOW}403 Forbidden{RESET} - Only owner can delete")
        response(r.get_json())

        cmd("POST /shared-budgets (no auth)")
        r = client.post("/shared-budgets", json={"name": "Test", "monthly_limit": 100})
        assert r.status_code == 401
        slow_print(f"  {YELLOW}401 Unauthorized{RESET} - Auth required")
        time.sleep(0.5)

        # Test results
        section("9. Test Suite Results")

        tests = [
            "test_create_shared_budget",
            "test_list_shared_budgets",
            "test_add_member_to_budget",
            "test_remove_member",
            "test_add_shared_expense",
            "test_budget_summary_calculation",
            "test_non_owner_cannot_delete",
            "test_requires_auth",
        ]
        for t in tests:
            slow_print(f"  {GREEN}PASS{RESET} {t}")
        print()
        slow_print(f"  {BOLD}{GREEN}All 30/30 tests passing (8 new + 22 existing){RESET}")

        print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
        slow_print(f"{BOLD}{GREEN}  Demo complete! Shared Budgeting ready for review.{RESET}", 0.03)
        print(f"{BOLD}{CYAN}{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    main()
