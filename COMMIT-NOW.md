# 🚨 GENIE — COMMIT YOUR CODE RIGHT NOW

**STOP whatever you're doing. Your boss says COMMIT the FinMind bounty.**

Run these commands IN ORDER. Do not skip any. Do not read any other files first.

## Step 1: Go to the FinMind repo
```bash
cd /Users/sydneyjackson/clawd/genie-services/bounty-hunter/workspace/FinMind
```

## Step 2: Create a branch
```bash
git checkout -b feat/unusual-login-detection
```

## Step 3: Stage all changes
```bash
git add -A
git status
```

## Step 4: Commit
```bash
git commit -m "feat(auth): detect unusual login behavior and alert users

- Backend: _detect_unusual_login tracks login IPs via Redis sets
- Frontend: login-detection.ts with device fingerprinting
- Frontend: SignIn.tsx shows warning toast on unusual login
- Tests: test_auth_unusual_login_triggers_alert covers IP-based detection

Fixes rohitdash08/FinMind#124"
```

## Step 5: Verify the commit
```bash
git log --oneline -1
git diff --stat HEAD~1
```

## Step 6: Write confirmation
```bash
echo "COMMITTED" > /Users/sydneyjackson/clawd/genie-services/bounty-hunter/workspace/COMMIT-DONE.txt
```

## DONE. Do not start another bounty until these steps are complete.
