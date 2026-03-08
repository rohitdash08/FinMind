# 🚨 GENIE — PUSH YOUR BRANCHES TO GITHUB NOW

**Your boss says: PUSH and open PRs so you can GET PAID.**

Code sitting local = $0. Code on GitHub = 💰. Do this NOW.

---

## Step 1: Set up remote (fork the repo first)

```bash
cd /Users/sydneyjackson/clawd/genie-services/bounty-hunter/workspace/FinMind

# Check if we have a fork remote
git remote -v

# If only "origin" pointing to rohitdash08, we need to fork first
# Use GitHub CLI to fork
gh repo fork rohitdash08/FinMind --clone=false --remote=true 2>/dev/null || true

# If gh isn't available, add our fork manually:
# git remote add fork https://github.com/YOUR_USERNAME/FinMind.git
```

## Step 2: Push Bounty #124 branch ($50)
```bash
git push origin feat/finmind-login-anomaly 2>/dev/null || git push fork feat/finmind-login-anomaly
```

## Step 3: Open PR for Bounty #124
```bash
gh pr create \
  --repo rohitdash08/FinMind \
  --head feat/finmind-login-anomaly \
  --title "feat(auth): detect unusual login behavior and alert users" \
  --body "## What this does
- Adds lightweight login anomaly detection (new IP/device detection)
- Frontend: \`loginDetector.ts\` with device fingerprinting
- Demo script: \`detect-login-anomaly-demo.js\`
- Full test coverage with \`login-detection.test.ts\` and SSR test

Fixes #124

## Testing
All 38 tests pass. Run \`npm test\` to verify."
```

## Step 4: Push Bounty #134 branch ($20)
```bash
git push origin feat/finmind-household-134 2>/dev/null || git push fork feat/finmind-household-134
```

## Step 5: Open PR for Bounty #134
```bash
gh pr create \
  --repo rohitdash08/FinMind \
  --head feat/finmind-household-134 \
  --title "feat: multi-user household collaboration" \
  --body "## What this does
- Household collaboration utility and UI component
- Scaffold household API with full CRUD
- removeMember API with tests
- All tests passing

Fixes #134

## Testing
All 38 tests pass including new household tests."
```

## Step 6: Confirm
```bash
echo "PRs OPENED" > /Users/sydneyjackson/clawd/genie-services/bounty-hunter/workspace/PR-DONE.txt
gh pr list --repo rohitdash08/FinMind --author @me
```

## IMPORTANT
- If `gh` CLI isn't authenticated, run: `gh auth login`
- If you can't push, you need to fork first
- DO NOT start another bounty until both PRs are open
- $70 is waiting for you. PUSH THE CODE.
