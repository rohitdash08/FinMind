#!/bin/bash
set -euo pipefail

# FinMind — Deployment Validation Script
# ───────────────────────────────────────
# Verifies all runtime acceptance criteria after deployment.
# Usage: ./scripts/validate-deploy.sh [BASE_URL]
# Example: ./scripts/validate-deploy.sh https://finmind.example.com

BASE_URL="${1:-http://localhost:8000}"
FRONTEND_URL="${2:-http://localhost:5173}"
PASS=0
FAIL=0

check() {
  local name="$1"
  local url="$2"
  local expected="${3:-200}"

  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 30 "$url" 2>/dev/null || echo "000")

  if [ "$STATUS" = "$expected" ]; then
    echo "  ✅ $name (HTTP $STATUS)"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $name (HTTP $STATUS, expected $expected)"
    FAIL=$((FAIL + 1))
  fi
}

check_json() {
  local name="$1"
  local url="$2"
  local key="$3"

  RESPONSE=$(curl -s --connect-timeout 10 --max-time 30 "$url" 2>/dev/null || echo "{}")
  VALUE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('$key',''))" 2>/dev/null || echo "")

  if [ -n "$VALUE" ] && [ "$VALUE" != "None" ]; then
    echo "  ✅ $name ($key=$VALUE)"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $name ($key not found)"
    FAIL=$((FAIL + 1))
  fi
}

echo "╔══════════════════════════════════════════╗"
echo "║  FinMind — Deployment Validation         ║"
echo "╚══════════════════════════════════════════╝"
echo "  Backend:  $BASE_URL"
echo "  Frontend: $FRONTEND_URL"
echo ""

# ── Backend Health ────────────────────────────────
echo "🔍 Backend Health:"
check "Health endpoint" "$BASE_URL/health"
check_json "Health status" "$BASE_URL/health" "status"

# ── Frontend ──────────────────────────────────────
echo ""
echo "🔍 Frontend:"
check "Frontend reachable" "$FRONTEND_URL"

# ── Auth Flows ────────────────────────────────────
echo ""
echo "🔍 Auth Flows:"
# Test registration endpoint exists
check "Register endpoint" "$BASE_URL/api/auth/register" "405"  # Method not allowed = endpoint exists
check "Login endpoint" "$BASE_URL/api/auth/login" "405"

# ── Core Modules ──────────────────────────────────
echo ""
echo "🔍 Core API Endpoints:"
check "Expenses API" "$BASE_URL/api/expenses" "401"  # Unauthorized = endpoint exists, auth required
check "Bills API" "$BASE_URL/api/bills" "401"
check "Reminders API" "$BASE_URL/api/reminders" "401"
check "Dashboard API" "$BASE_URL/api/dashboard" "401"
check "Insights API" "$BASE_URL/api/insights" "401"

# ── Summary ───────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
TOTAL=$((PASS + FAIL))
echo "  Results: $PASS/$TOTAL passed"

if [ "$FAIL" -gt 0 ]; then
  echo "  ⚠️  $FAIL check(s) failed"
  exit 1
else
  echo "  ✅ All checks passed!"
  exit 0
fi
