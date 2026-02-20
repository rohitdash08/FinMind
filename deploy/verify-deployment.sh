#!/bin/bash
# Deployment verification script for FinMind
# Usage: ./verify-deployment.sh <backend-url> <frontend-url>

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BACKEND_URL="${1:-http://localhost:8000}"
FRONTEND_URL="${2:-http://localhost:3000}"

echo -e "${YELLOW}╔════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║     FinMind Deployment Verification            ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Backend URL:  ${BACKEND_URL}"
echo -e "Frontend URL: ${FRONTEND_URL}"
echo ""

# Function to check endpoint
check_endpoint() {
    local url=$1
    local expected=$2
    local description=$3
    
    echo -n "Checking ${description}... "
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "${url}" 2>/dev/null || echo "000")
    
    if [ "$response" -eq "$expected" ]; then
        echo -e "${GREEN}✓ OK${NC} (HTTP ${response})"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC} (HTTP ${response}, expected ${expected})"
        return 1
    fi
}

# Function to check JSON response
check_json_endpoint() {
    local url=$1
    local key=$2
    local expected_value=$3
    local description=$4
    
    echo -n "Checking ${description}... "
    
    response=$(curl -s "${url}" 2>/dev/null || echo "{}")
    value=$(echo "$response" | grep -o "\"${key}\":\"[^\"]*\"" | cut -d'"' -f4 || echo "")
    
    if [ "$value" = "$expected_value" ]; then
        echo -e "${GREEN}✓ OK${NC} (${key}=${value})"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC} (${key}=${value}, expected ${expected_value})"
        echo "  Response: ${response}"
        return 1
    fi
}

TESTS_PASSED=0
TESTS_FAILED=0

echo -e "${YELLOW}Backend Health Checks:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Backend health endpoint
if check_json_endpoint "${BACKEND_URL}/health" "status" "ok" "Backend health endpoint"; then
    ((TESTS_PASSED++))
else
    ((TESTS_FAILED++))
fi

# Backend readiness endpoint
if check_json_endpoint "${BACKEND_URL}/ready" "status" "ready" "Backend readiness endpoint"; then
    ((TESTS_PASSED++))
else
    ((TESTS_FAILED++))
fi

# Backend API docs
if check_endpoint "${BACKEND_URL}/docs" 200 "Backend API documentation"; then
    ((TESTS_PASSED++))
else
    ((TESTS_FAILED++))
fi

echo ""
echo -e "${YELLOW}Frontend Checks:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Frontend root
if check_endpoint "${FRONTEND_URL}/" 200 "Frontend homepage"; then
    ((TESTS_PASSED++))
else
    ((TESTS_FAILED++))
fi

echo ""
echo -e "${YELLOW}Database Connection:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if database is connected via ready endpoint
response=$(curl -s "${BACKEND_URL}/ready" 2>/dev/null || echo "{}")
db_status=$(echo "$response" | grep -o "\"database\":\"[^\"]*\"" | cut -d'"' -f4 || echo "")

echo -n "Checking database connection... "
if [ "$db_status" = "connected" ]; then
    echo -e "${GREEN}✓ CONNECTED${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ NOT CONNECTED${NC}"
    ((TESTS_FAILED++))
fi

echo ""
echo -e "${YELLOW}Summary:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "Tests Passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Tests Failed: ${RED}${TESTS_FAILED}${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ All checks passed! Deployment verified.    ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ✗ Some checks failed. Review logs above.     ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════╝${NC}"
    exit 1
fi
