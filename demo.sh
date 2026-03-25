#!/bin/bash
# FinMind Feature Demo - PRs #607, #608, #609
BASE=http://127.0.0.1:5555

echo "======================================"
echo " FinMind Feature Demo"
echo "======================================"
echo ""

# Register and login
echo ">>> Register user"
curl -s -X POST $BASE/auth/register -H "Content-Type: application/json" \
  -d '{"email":"demo@test.com","password":"demo1234"}' | python3 -m json.tool
echo ""

echo ">>> Login"
TOKEN=$(curl -s -X POST $BASE/auth/login -H "Content-Type: application/json" \
  -d '{"email":"demo@test.com","password":"demo1234"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Got token: ${TOKEN:0:20}..."
AUTH="Authorization: Bearer $TOKEN"
echo ""

# Add some expenses for digest
echo "======================================"
echo " PR #607: Weekly Digest"
echo "======================================"
echo ""

echo ">>> Adding expenses for last week..."
for i in 1 2 3 4 5; do
  DAY=$(date -d "last monday + ${i} days" +%Y-%m-%d 2>/dev/null || date -v-7d +%Y-%m-%d)
  curl -s -X POST $BASE/expenses -H "$AUTH" -H "Content-Type: application/json" \
    -d "{\"amount\":$((50 + i * 15)),\"notes\":\"Expense day $i\",\"spent_at\":\"$DAY\"}" > /dev/null
done
echo "Added 5 expenses"
echo ""

echo ">>> POST /digest/generate"
curl -s -X POST $BASE/digest/generate -H "$AUTH" | python3 -m json.tool
echo ""

echo ">>> GET /digest/latest"
curl -s $BASE/digest/latest -H "$AUTH" | python3 -m json.tool
echo ""

echo ">>> GET /digest/history"
curl -s "$BASE/digest/history?limit=5" -H "$AUTH" | python3 -m json.tool
echo ""

# Savings Goals
echo "======================================"
echo " PR #608: Savings Goals"
echo "======================================"
echo ""

echo ">>> POST /goals/ (create goal)"
curl -s -X POST $BASE/goals/ -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Emergency Fund","target_amount":10000,"currency":"EUR","deadline":"2026-12-31"}' | python3 -m json.tool
echo ""

echo ">>> POST /goals/1/contribute (add 2500)"
curl -s -X POST $BASE/goals/1/contribute -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"amount":2500,"note":"First deposit"}' | python3 -m json.tool
echo ""

echo ">>> POST /goals/1/contribute (add 5000)"
curl -s -X POST $BASE/goals/1/contribute -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"amount":5000,"note":"Bonus savings"}' | python3 -m json.tool
echo ""

echo ">>> GET /goals/1/progress (75% with milestones)"
curl -s $BASE/goals/1/progress -H "$AUTH" | python3 -m json.tool
echo ""

echo ">>> GET /goals/1/contributions"
curl -s $BASE/goals/1/contributions -H "$AUTH" | python3 -m json.tool
echo ""

# Multi-account
echo "======================================"
echo " PR #609: Multi-Account Dashboard"
echo "======================================"
echo ""

echo ">>> POST /accounts/ (checking)"
curl -s -X POST $BASE/accounts/ -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Main Checking","account_type":"checking","balance":5000,"currency":"EUR"}' | python3 -m json.tool
echo ""

echo ">>> POST /accounts/ (savings)"
curl -s -X POST $BASE/accounts/ -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Savings","account_type":"savings","balance":15000,"currency":"EUR"}' | python3 -m json.tool
echo ""

echo ">>> POST /accounts/ (credit card)"
curl -s -X POST $BASE/accounts/ -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Credit Card","account_type":"credit","balance":2000,"currency":"EUR"}' | python3 -m json.tool
echo ""

echo ">>> GET /accounts/overview (net worth)"
curl -s $BASE/accounts/overview -H "$AUTH" | python3 -m json.tool
echo ""

echo "======================================"
echo " Demo Complete!"
echo "======================================"
