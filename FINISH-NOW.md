# 🚨 GENIE — FINISH THE BOUNTY NOW

**STOP reading files. You have everything you need. Execute these steps IN ORDER.**

You already wrote `login-detection.ts` and `test_auth.py`. Now FINISH IT.

---

## STEP 1: Patch SignIn.tsx (ONE edit)

Run this exact command to patch SignIn.tsx:

```bash
cd /Users/sydneyjackson/clawd/genie-services/bounty-hunter/workspace/finmind

python3 << 'PATCH'
import re

path = "app/src/pages/SignIn.tsx"
with open(path) as f:
    code = f.read()

# Add import at top after last import line
import_line = "import { getDeviceFingerprint, checkForUnusualLogin } from '@/utils/login-detection';\n"
# Find the last import statement
last_import = code.rfind("import ")
end_of_last_import = code.index("\n", last_import) + 1
if "login-detection" not in code:
    code = code[:end_of_last_import] + import_line + code[end_of_last_import:]

# Add unusual login check after the welcome toast line
old = "toast({ title: 'Welcome back', description: 'You have successfully signed in.' });"
new = """toast({ title: 'Welcome back', description: 'You have successfully signed in.' });
      // Unusual login detection
      const fp = getDeviceFingerprint();
      const isUnusual = checkForUnusualLogin(fp);
      if (isUnusual || res.unusual_login) {
        toast({ variant: 'destructive', title: '⚠️ Unusual login detected', description: 'This login is from a new device or location. If this wasn\\'t you, please change your password.' });
      }"""
code = code.replace(old, new)

with open(path, "w") as f:
    f.write(code)
print("✅ SignIn.tsx patched!")
PATCH
```

## STEP 2: Verify the patch worked

```bash
grep -n "unusual\|fingerprint\|login-detection" app/src/pages/SignIn.tsx
```

You should see 3+ matches.

## STEP 3: Create a git branch and commit

```bash
cd /Users/sydneyjackson/clawd/genie-services/bounty-hunter/workspace/finmind
git checkout -b feat/unusual-login-detection
git add -A
git status
git commit -m "feat(auth): detect unusual login behavior and alert users

- Enhanced backend _detect_unusual_login with IP tracking via Redis
- Added frontend device fingerprinting (login-detection.ts)
- Added unusual login toast alert in SignIn.tsx
- Added test_auth_unusual_login_triggers_alert test

Fixes #124"
```

## STEP 4: Write completion summary

```bash
cat > /Users/sydneyjackson/clawd/genie-services/bounty-hunter/workspace/BOUNTY-COMPLETE.md << 'DONE'
# ✅ BOUNTY #124 COMPLETE

## Files Changed
1. `packages/backend/app/routes/auth.py` — _detect_unusual_login (IP tracking via Redis)
2. `packages/backend/tests/test_auth.py` — Added unusual login test
3. `app/src/utils/login-detection.ts` — NEW: Frontend device fingerprinting
4. `app/src/pages/SignIn.tsx` — Integrated unusual login alert toast

## How It Works
- Backend: Tracks login IPs per user in Redis. New IP = unusual.
- Frontend: Fingerprints device (UA + screen + language). New device = unusual.
- Both signals trigger a warning toast on login.

## Ready for PR submission
DONE
```

## THEN STOP. You're done with this bounty. 🎉

**DO NOT start another bounty. DO NOT read more files. Just execute Steps 1-4.**
