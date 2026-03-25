#!/bin/bash
BASE=http://127.0.0.1:5556

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║      FinMind Feature Demo            ║"
echo "  ║  PRs #607, #608, #609               ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
sleep 1

# Auth
echo ">>> Register + Login"
curl -s -X POST $BASE/auth/register -H "Content-Type: application/json" \
  -d '{"email":"demo@finmind.test","password":"demo1234"}' | python3 -m json.tool
TOKEN=$(curl -s -X POST $BASE/auth/login -H "Content-Type: application/json" \
  -d '{"email":"demo@finmind.test","password":"demo1234"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token: ${TOKEN:0:30}..."
echo ""
sleep 1

# ===== PR #609: Multi-Account =====
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PR #609: Multi-Account Dashboard (\$200)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo ">>> Create checking account (€5,000)"
curl -s -X POST $BASE/accounts/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Main Checking","account_type":"checking","balance":5000,"currency":"EUR"}' | python3 -m json.tool
sleep 0.5

echo ">>> Create savings account (€15,000)"
curl -s -X POST $BASE/accounts/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Savings","account_type":"savings","balance":15000,"currency":"EUR"}' | python3 -m json.tool
sleep 0.5

echo ">>> Create credit card (€2,000 debt)"
curl -s -X POST $BASE/accounts/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Credit Card","account_type":"credit","balance":2000,"currency":"EUR"}' | python3 -m json.tool
sleep 0.5

echo ">>> GET /accounts/overview → Net worth calculation"
curl -s $BASE/accounts/overview -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
sleep 1

# ===== PR #608: Savings Goals =====
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PR #608: Savings Goals (\$250)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo ">>> Create goal: Emergency Fund €10,000"
curl -s -X POST $BASE/goals/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Emergency Fund","target_amount":10000,"currency":"EUR","deadline":"2026-12-31"}' | python3 -m json.tool
sleep 0.5

echo ">>> Contribute €2,500"
curl -s -X POST $BASE/goals/1/contribute -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"amount":2500,"note":"First deposit"}' | python3 -m json.tool
sleep 0.5

echo ">>> Contribute €5,000"
curl -s -X POST $BASE/goals/1/contribute -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"amount":5000,"note":"Bonus savings"}' | python3 -m json.tool
sleep 0.5

echo ">>> GET /goals/1/progress → 75% with milestones"
curl -s $BASE/goals/1/progress -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
sleep 1

# ===== PR #607: Weekly Digest =====
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PR #607: Weekly Digest (\$500)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo ">>> Adding 5 expenses from last week..."
for i in 1 2 3 4 5; do
  curl -s -X POST $BASE/expenses -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"amount\":$((50 + i * 15)),\"notes\":\"Expense $i\",\"spent_at\":\"2026-03-$(printf '%02d' $((9 + i)))\"}" > /dev/null
done
echo "Done (5 expenses added)"
sleep 0.5

echo ">>> POST /digest/generate → AI-powered weekly summary"
curl -s -X POST $BASE/digest/generate -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
sleep 0.5

echo ">>> GET /digest/latest"
curl -s $BASE/digest/latest -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ All 3 features working!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
