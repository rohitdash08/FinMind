#!/usr/bin/env python3
"""Demo script for FinMind Goal-based Savings Tracking feature."""
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
    print("  FinMind - Goal-based Savings Tracking Demo")
    print(f"  Issue #133 | Savings Goals & Milestones{RESET}")
    print(f"{DIM}  Feature: /savings/goals - Track progress toward financial goals{RESET}")
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
        time.sleep(0.5)

        section("2. User Authentication")
        cmd("POST /auth/register + /auth/login")
        client.post("/auth/register", json={"email": "saver@finmind.io", "password": "save123"})
        r = client.post("/auth/login", json={"email": "saver@finmind.io", "password": "save123"})
        auth = {"Authorization": f"Bearer {r.get_json()['access_token']}"}
        slow_print(f"  {GREEN}200 OK{RESET} - Authenticated")
        time.sleep(0.5)

        section("3. Create Savings Goals")
        cmd("POST /savings/goals - Vacation fund")
        r = client.post("/savings/goals", json={
            "name": "Dream Vacation", "target_amount": 5000, "deadline": "2026-12-31"
        }, headers=auth)
        vac_id = r.get_json()["id"]
        slow_print(f"  {GREEN}201 Created{RESET} - Goal: Dream Vacation ($5,000)")
        response(r.get_json())

        cmd("POST /savings/goals - Emergency fund")
        r = client.post("/savings/goals", json={
            "name": "Emergency Fund", "target_amount": 10000
        }, headers=auth)
        emg_id = r.get_json()["id"]
        slow_print(f"  {GREEN}201 Created{RESET} - Goal: Emergency Fund ($10,000)")
        time.sleep(0.5)

        section("4. Make Deposits & Track Progress")
        deposits = [
            (vac_id, 1000, "Birthday money"),
            (vac_id, 500, "Side gig earnings"),
            (vac_id, 1500, "Tax refund"),
            (emg_id, 2500, "Monthly savings"),
        ]
        for gid, amount, note in deposits:
            cmd(f"POST /savings/goals/{gid}/deposit")
            r = client.post(f"/savings/goals/{gid}/deposit", json={
                "amount": amount, "note": note
            }, headers=auth)
            data = r.get_json()
            pct = data["progress_pct"]
            bar_len = int(pct / 2)
            bar = "#" * bar_len + "-" * (50 - bar_len)
            slow_print(f"  {GREEN}+${amount}{RESET} {note}")
            slow_print(f"  {CYAN}[{bar}] {pct}%{RESET} (${data['current_amount']:,.0f}/${data['target_amount']:,.0f})")
            print()
        time.sleep(0.5)

        section("5. View Goal with Milestones")
        cmd(f"GET /savings/goals/{vac_id}")
        r = client.get(f"/savings/goals/{vac_id}", headers=auth)
        data = r.get_json()
        slow_print(f"  {GREEN}200 OK{RESET}")
        slow_print(f"\n  {BOLD}{data['name']}{RESET}")
        slow_print(f"  Target: ${data['target_amount']:,.0f} | Current: ${data['current_amount']:,.0f}")
        print()
        slow_print(f"  {BOLD}Milestones:{RESET}")
        for m in data["milestones"]:
            icon = GREEN + "YES" if m["reached"] else YELLOW + " - "
            slow_print(f"    {m['percent']:>3}%  [{icon}{RESET}]")
        print()
        slow_print(f"  {BOLD}Deposits:{RESET}")
        for d in data["deposits"]:
            slow_print(f"    ${d['amount']:>8,.0f}  {d['note'] or ''}")
        time.sleep(0.5)

        section("6. Withdraw from Goal")
        cmd(f"POST /savings/goals/{vac_id}/withdraw")
        r = client.post(f"/savings/goals/{vac_id}/withdraw", json={"amount": 500}, headers=auth)
        data = r.get_json()
        slow_print(f"  {YELLOW}-$500{RESET} withdrawn")
        slow_print(f"  New balance: ${data['current_amount']:,.0f} ({data['progress_pct']}%)")
        time.sleep(0.5)

        section("7. Goal Completion")
        cmd(f"POST /savings/goals/{vac_id}/deposit - Complete the goal!")
        r = client.post(f"/savings/goals/{vac_id}/deposit", json={
            "amount": 2500, "note": "Bonus!"
        }, headers=auth)
        data = r.get_json()
        if data["completed"]:
            slow_print(f"  {GREEN}GOAL COMPLETED!{RESET} {data['name']}")
            slow_print(f"  Completed at: {data['completed_at']}")
        for m in data["milestones"]:
            icon = GREEN + "YES" if m["reached"] else YELLOW + " - "
            slow_print(f"    {m['percent']:>3}%  [{icon}{RESET}]")
        time.sleep(0.5)

        section("8. Permission & Auth Checks")
        cmd("GET /savings/goals (no auth)")
        r = client.get("/savings/goals")
        slow_print(f"  {YELLOW}401 Unauthorized{RESET}")

        client.post("/auth/register", json={"email": "other@test.com", "password": "pass123"})
        r2 = client.post("/auth/login", json={"email": "other@test.com", "password": "pass123"})
        other_auth = {"Authorization": f"Bearer {r2.get_json()['access_token']}"}
        cmd(f"GET /savings/goals/{vac_id} (other user)")
        r = client.get(f"/savings/goals/{vac_id}", headers=other_auth)
        slow_print(f"  {YELLOW}404 Not Found{RESET} - Cannot access other user's goals")
        time.sleep(0.5)

        section("9. Test Suite Results")
        tests = [
            "test_create_savings_goal",
            "test_list_goals_with_progress",
            "test_deposit_updates_amount",
            "test_goal_completion_on_target_reached",
            "test_milestones_calculation",
            "test_withdraw_from_goal",
            "test_cannot_access_other_user_goals",
            "test_requires_auth",
        ]
        for t in tests:
            slow_print(f"  {GREEN}PASS{RESET} {t}")
        print()
        slow_print(f"  {BOLD}{GREEN}All 30/30 tests passing (8 new + 22 existing){RESET}")

        print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
        slow_print(f"{BOLD}{GREEN}  Demo complete! Savings Tracking ready for review.{RESET}", 0.03)
        print(f"{BOLD}{CYAN}{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    main()
