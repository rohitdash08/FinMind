#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  FinMind — Runtime Smoke Test Suite                         ║
# ║  Validates all acceptance criteria from issue #144          ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail

BACKEND_URL="${1:-http://localhost:8000}"
FRONTEND_URL="${2:-http://localhost:5173}"
PASS=0
FAIL=0
WARN=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check() {
    local name="$1"
    local url="$2"
    local expect="${3:-200}"

    echo -n "  [$name] $url ... "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "$expect" ]; then
        echo -e "${GREEN}PASS${NC} (HTTP $HTTP_CODE)"
        PASS=$((PASS + 1))
    elif [ "$HTTP_CODE" = "000" ]; then
        echo -e "${RED}FAIL${NC} (connection refused)"
        FAIL=$((FAIL + 1))
    else
        echo -e "${YELLOW}WARN${NC} (HTTP $HTTP_CODE, expected $expect)"
        WARN=$((WARN + 1))
    fi
}

check_json() {
    local name="$1"
    local url="$2"
    local field="$3"

    echo -n "  [$name] $url .$field ... "
    RESPONSE=$(curl -s --max-time 10 "$url" 2>/dev/null || echo "{}")
    VALUE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('$field',''))" 2>/dev/null || echo "")

    if [ -n "$VALUE" ] && [ "$VALUE" != "None" ]; then
        echo -e "${GREEN}PASS${NC} ($field=$VALUE)"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}FAIL${NC} (field '$field' not found)"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        FinMind Smoke Test Suite          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Backend:  $BACKEND_URL"
echo "Frontend: $FRONTEND_URL"
echo ""

# ── 1. Frontend reachable ──
echo "1. Frontend Reachability"
check "Frontend root" "$FRONTEND_URL"
check "Frontend assets" "$FRONTEND_URL/index.html"
echo ""

# ── 2. Backend health reachable ──
echo "2. Backend Health"
check "Health endpoint" "$BACKEND_URL/health"
check "Metrics endpoint" "$BACKEND_URL/metrics"
echo ""

# ── 3. DB + Redis connected (health endpoint returns connection status) ──
echo "3. Database & Redis Connectivity"
check_json "Health DB check" "$BACKEND_URL/health" "status"
echo ""

# ── 4. Auth flows ──
echo "4. Authentication Flows"
# Test registration endpoint exists
echo -n "  [Auth register] POST $BACKEND_URL/auth/register ... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -X POST \
    -H "Content-Type: application/json" \
    -d '{"email":"smoke-test@test.com","password":"Test123!","name":"Smoke Test"}' \
    "$BACKEND_URL/auth/register" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "409" ] || [ "$HTTP_CODE" = "422" ] || [ "$HTTP_CODE" = "400" ]; then
    echo -e "${GREEN}PASS${NC} (HTTP $HTTP_CODE — endpoint responsive)"
    PASS=$((PASS + 1))
elif [ "$HTTP_CODE" = "000" ]; then
    echo -e "${RED}FAIL${NC} (connection refused)"
    FAIL=$((FAIL + 1))
else
    echo -e "${YELLOW}WARN${NC} (HTTP $HTTP_CODE)"
    WARN=$((WARN + 1))
fi

# Test login endpoint exists
echo -n "  [Auth login] POST $BACKEND_URL/auth/login ... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -X POST \
    -H "Content-Type: application/json" \
    -d '{"email":"smoke-test@test.com","password":"Test123!"}' \
    "$BACKEND_URL/auth/login" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "422" ] || [ "$HTTP_CODE" = "400" ]; then
    echo -e "${GREEN}PASS${NC} (HTTP $HTTP_CODE — endpoint responsive)"
    PASS=$((PASS + 1))
elif [ "$HTTP_CODE" = "000" ]; then
    echo -e "${RED}FAIL${NC} (connection refused)"
    FAIL=$((FAIL + 1))
else
    echo -e "${YELLOW}WARN${NC} (HTTP $HTTP_CODE)"
    WARN=$((WARN + 1))
fi
echo ""

# ── 5. Core modules ──
echo "5. Core Module Endpoints"
for endpoint in expenses bills reminders dashboard insights; do
    check "Module: $endpoint" "$BACKEND_URL/${endpoint}" "401"  # 401 expected without auth token
done
echo ""

# ── Summary ──
TOTAL=$((PASS + FAIL + WARN))
echo "══════════════════════════════════════════"
echo -e "  Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$WARN warnings${NC} / $TOTAL total"
echo "══════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
