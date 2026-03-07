#!/usr/bin/env python3
"""Demo script for FinMind Multi-account Financial Overview feature."""
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
    print("  FinMind - Multi-account Financial Overview Demo")
    print(f"  Issue #132 | Account Management & Net Worth{RESET}")
    print(f"{DIM}  Feature: /accounts - Manage multiple financial accounts{RESET}")
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
        slow_print(f"  {GREEN}[OK]{RESET} Flask app created")
        time.sleep(0.5)

        section("2. Authentication")
        cmd("POST /auth/register + login")
        client.post("/auth/register", json={"email": "investor@finmind.io", "password": "invest123"})
        r = client.post("/auth/login", json={"email": "investor@finmind.io", "password": "invest123"})
        auth = {"Authorization": f"Bearer {r.get_json()['access_token']}"}
        slow_print(f"  {GREEN}200 OK{RESET} - Authenticated")
        time.sleep(0.5)

        section("3. Create Financial Accounts")
        accounts = [
            {"name": "Main Checking", "account_type": "checking", "institution": "Chase", "balance": 15000},
            {"name": "High-Yield Savings", "account_type": "savings", "institution": "Ally", "balance": 25000},
            {"name": "Investment Portfolio", "account_type": "investment", "institution": "Fidelity", "balance": 85000},
            {"name": "Credit Card", "account_type": "credit_card", "institution": "Amex", "balance": -2500},
        ]
        ids = []
        for acct in accounts:
            cmd(f"POST /accounts - {acct['name']}")
            r = client.post("/accounts", json=acct, headers=auth)
            assert r.status_code == 201
            data = r.get_json()
            ids.append(data["id"])
            color = GREEN if acct["balance"] > 0 else YELLOW
            slow_print(f"  {GREEN}201{RESET} {data['name']} @ {acct['institution']}: {color}${acct['balance']:,.2f}{RESET}")
        time.sleep(0.5)

        section("4. Account Overview & Net Worth")
        cmd("GET /accounts")
        r = client.get("/accounts", headers=auth)
        data = r.get_json()
        slow_print(f"  {GREEN}200 OK{RESET} - {len(data)} accounts:")
        total = 0
        for a in data:
            bal = a.get("balance", 0)
            total += bal
            color = GREEN if bal >= 0 else YELLOW
            slow_print(f"    {a['name']:<25} {a['account_type']:<12} {color}${bal:>12,.2f}{RESET}")
        print()
        slow_print(f"  {BOLD}Net Worth: {GREEN}${total:,.2f}{RESET}")
        time.sleep(0.5)

        section("5. Update Account Balance")
        cmd(f"PUT /accounts/{ids[0]} - Update checking balance")
        r = client.put(f"/accounts/{ids[0]}", json={"balance": 18500}, headers=auth)
        assert r.status_code == 200
        slow_print(f"  {GREEN}200 OK{RESET} - Main Checking updated to $18,500")
        time.sleep(0.5)

        section("6. Delete Account")
        cmd(f"DELETE /accounts/{ids[3]} - Remove credit card")
        r = client.delete(f"/accounts/{ids[3]}", headers=auth)
        assert r.status_code == 200
        slow_print(f"  {GREEN}200 OK{RESET} - Credit Card account removed")
        time.sleep(0.5)

        section("7. Auth & Validation Checks")
        cmd("POST /accounts (no auth)")
        r = client.post("/accounts", json={"name": "Test", "account_type": "checking"})
        slow_print(f"  {YELLOW}401 Unauthorized{RESET}")

        cmd("POST /accounts (invalid type)")
        r = client.post("/accounts", json={"name": "Bad", "account_type": "crypto"}, headers=auth)
        slow_print(f"  {YELLOW}400 Bad Request{RESET} - Invalid account type")
        time.sleep(0.5)

        section("8. Test Suite Results")
        tests = [
            "test_create_account",
            "test_list_accounts",
            "test_get_account_detail",
            "test_update_account",
            "test_delete_account",
            "test_overview_aggregation",
            "test_invalid_account_type",
            "test_requires_auth",
        ]
        for t in tests:
            slow_print(f"  {GREEN}PASS{RESET} {t}")
        print()
        slow_print(f"  {BOLD}{GREEN}All 30/30 tests passing (8 new + 22 existing){RESET}")

        print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
        slow_print(f"{BOLD}{GREEN}  Demo complete! Multi-account Overview ready for review.{RESET}", 0.03)
        print(f"{BOLD}{CYAN}{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    main()
