#!/usr/bin/env python3
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from datetime import datetime, timezone
from typing import Any


def _request(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> tuple[int, str, dict[str, Any] | None]:
    body = None
    req_headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)

    request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            data = None
            if "application/json" in (response.headers.get("Content-Type") or ""):
                data = json.loads(text)
            return response.status, text, data
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        data = None
        if "application/json" in (exc.headers.get("Content-Type") or ""):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
        return exc.code, text, data


def _wait_for(url: str, timeout: int = 180, interval: int = 3) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _, _ = _request("GET", url, timeout=5)
            if 200 <= status < 500:
                return
        except Exception:
            pass
        time.sleep(interval)
    raise RuntimeError(f"Timed out waiting for {url}")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test a FinMind deployment")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend-url", default="http://127.0.0.1:8081")
    parser.add_argument("--provider-name", default="deployment")
    parser.add_argument("--commit-sha", default="")
    args = parser.parse_args()

    api = args.api_base_url.rstrip("/")
    frontend = args.frontend_url.rstrip("/")
    validated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    verified_modules: list[str] = []

    print(f"provider={args.provider_name}")
    if args.commit_sha:
        print(f"commit_sha={args.commit_sha}")
    print(f"validated_at_utc={validated_at}")
    print(f"frontend_url={frontend}")
    print(f"api_url={api}")
    print(f"health_url={api}/health/ready")

    _wait_for(f"{api}/health")
    _wait_for(frontend)
    print("waits=backend health reachable, frontend reachable")

    health_status, _, health_data = _request("GET", f"{api}/health")
    _assert(health_status == 200, "backend health endpoint did not return 200")
    _assert((health_data or {}).get("status") == "ok", "backend health payload invalid")
    print(f"health_status={health_status}")

    ready_status, _, ready_data = _request("GET", f"{api}/health/ready")
    _assert(ready_status == 200, "backend readiness endpoint did not return 200")
    _assert((ready_data or {}).get("status") == "ok", "backend readiness payload invalid")
    checks = (ready_data or {}).get("checks") or {}
    _assert(checks.get("database") == "connected", "database readiness check failed")
    _assert(checks.get("redis") == "connected", "redis readiness check failed")
    print("health_ready_json=" + json.dumps(ready_data or {}, sort_keys=True))
    verified_modules.extend(["backend/health", "backend/readiness", "database", "redis"])

    frontend_status, frontend_body, _ = _request("GET", frontend)
    _assert(frontend_status == 200, "frontend root is not reachable")
    _assert("FinMind" in frontend_body, "frontend root did not render FinMind shell")
    print(f"frontend_status={frontend_status}")
    verified_modules.append("frontend shell")

    email = f"deploy-smoke-{int(time.time())}@example.com"
    password = "SmokePassword123!"
    register_status, _, _ = _request(
        "POST",
        f"{api}/auth/register",
        payload={"email": email, "password": password},
    )
    _assert(register_status in (200, 201), "register flow failed")
    print(f"register_status={register_status}")

    login_status, _, login_data = _request(
        "POST",
        f"{api}/auth/login",
        payload={"email": email, "password": password},
    )
    _assert(login_status == 200, "login flow failed")
    access_token = (login_data or {}).get("access_token")
    _assert(bool(access_token), "login did not return access token")
    auth = {"Authorization": f"Bearer {access_token}"}
    print(f"login_status={login_status}")
    verified_modules.extend(["auth/register", "auth/login"])

    me_status, _, me_data = _request("GET", f"{api}/auth/me", headers=auth)
    _assert(me_status == 200, "auth/me failed")
    _assert((me_data or {}).get("email") == email, "auth/me returned unexpected user")
    print(f"auth_me_status={me_status}")
    verified_modules.append("auth/me")

    category_status, _, _ = _request(
        "POST",
        f"{api}/categories",
        payload={"name": "Smoke Category"},
        headers=auth,
    )
    _assert(category_status in (201, 409), "category create failed")
    categories_status, _, categories_data = _request(
        "GET", f"{api}/categories", headers=auth
    )
    _assert(categories_status == 200, "category list failed")
    categories = categories_data or []
    _assert(len(categories) >= 1, "category list empty after create")
    category_id = categories[0]["id"]
    print(f"categories_status=create:{category_status},list:{categories_status}")
    verified_modules.append("categories")

    today = date.today()
    due = today + timedelta(days=5)
    current_month = today.strftime("%Y-%m")

    expense_status, _, expense_data = _request(
        "POST",
        f"{api}/expenses",
        payload={
            "amount": 42.5,
            "currency": "USD",
            "category_id": category_id,
            "description": "Smoke expense",
            "date": today.isoformat(),
            "expense_type": "EXPENSE",
        },
        headers=auth,
    )
    _assert(expense_status == 201, "expense create failed")
    _assert(
        (expense_data or {}).get("description") == "Smoke expense",
        "expense payload mismatch",
    )
    print(f"expense_status={expense_status}")
    verified_modules.append("expenses")

    bill_status, _, bill_data = _request(
        "POST",
        f"{api}/bills",
        payload={
            "name": "Smoke bill",
            "amount": 18.75,
            "currency": "USD",
            "next_due_date": due.isoformat(),
            "cadence": "MONTHLY",
            "channel_email": True,
            "channel_whatsapp": False,
        },
        headers=auth,
    )
    _assert(bill_status == 201, "bill create failed")
    bill_id = (bill_data or {}).get("id")
    _assert(bool(bill_id), "bill id missing")
    print(f"bill_status={bill_status}")
    verified_modules.append("bills")

    reminders_status, _, reminders_data = _request(
        "POST",
        f"{api}/reminders/bills/{bill_id}/schedule",
        headers=auth,
    )
    _assert(reminders_status == 200, "bill reminder scheduling failed")
    _assert(
        (reminders_data or {}).get("created", -1) >= 0,
        "reminder schedule payload invalid",
    )
    print(f"reminders_schedule_status={reminders_status}")

    reminders_list_status, _, reminders_list_data = _request(
        "GET", f"{api}/reminders", headers=auth
    )
    _assert(reminders_list_status == 200, "reminder list failed")
    _assert(isinstance(reminders_list_data, list), "reminders list payload invalid")
    print(f"reminders_list_status={reminders_list_status}")
    verified_modules.append("reminders")

    dashboard_status, _, dashboard_data = _request(
        "GET",
        f"{api}/dashboard/summary?month={urllib.parse.quote(current_month)}",
        headers=auth,
    )
    _assert(dashboard_status == 200, "dashboard summary failed")
    _assert("summary" in (dashboard_data or {}), "dashboard summary payload missing")
    _assert(
        isinstance((dashboard_data or {}).get("upcoming_bills"), list),
        "dashboard upcoming bills missing",
    )
    print(f"dashboard_status={dashboard_status}")
    verified_modules.append("dashboard")

    insights_status, _, insights_data = _request(
        "GET",
        f"{api}/insights/budget-suggestion?month={urllib.parse.quote(current_month)}",
        headers=auth,
    )
    _assert(insights_status == 200, "insights endpoint failed")
    _assert((insights_data or {}).get("month") == current_month, "insights month mismatch")
    print(f"insights_status={insights_status}")
    verified_modules.append("insights")

    print("verified_modules=" + ", ".join(verified_modules))
    print("FinMind deployment smoke check passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Smoke check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
