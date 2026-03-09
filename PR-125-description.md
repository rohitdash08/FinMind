# feat(login-detection): normalize history across array and legacy formats; exact UA+IP matching; MAX_HISTORY=5; add tests

What this changes
- FinMind login anomaly detector now:
  - Normalizes history data to an array regardless of whether it was stored as an array or a legacy object (e.g., { lastUserAgent, lastIp, lastTimestamp }).
  - Uses exact UA+IP matching to determine unusual logins. If the current pair of userAgent + ip matches an existing history entry, the login is not unusual.
  - Binds the history to a MAX_HISTORY of 5 entries to prevent unbounded growth.
  - Updates history only when a new, unseen pair appears; otherwise keeps existing history.

Tests
- Updated and added tests to cover array and legacy formats, max history clipping, and both unusual and non-unusual scenarios.
- See app/src/__tests__/login-detection.test.ts for unit tests and related integration tests under app/src/__tests__.

Files touched
- app/src/utils/login-detection.ts

How to run tests
- From project root: 
  - cd /Users/sydneyjackson/clawd/genie-services/bounty-hunter/workspace/finmind
  - npm install
  - npm test

PR status and notes
- This patch is intended to be submitted as bounty #125. Please replace the PR URL and bounty references once created on GitHub.
- Closes #125
