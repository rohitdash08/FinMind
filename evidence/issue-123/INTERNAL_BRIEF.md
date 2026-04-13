Repo: rohitdash08/FinMind
Issue: #123, Reminder reliability tracking & delivery metrics
Maintainer activity: issue is active, with multiple prior attempts and recent reminder-related closes, so the route is competitive and proof needs to be tight.
Problem: `POST /reminders/run` could previously mark reminders sent even when delivery failed, which hides failure and breaks reliability tracking.
Smallest valid fix: only mark a reminder sent after `send_reminder()` succeeds, return explicit processed/failed counts, and keep failed reminders unsent for future retry.
Likely maintainer objection: this changes job semantics without implementing full retry backoff or metrics dashboard.
Required proof: regression test that failed delivery stays unsent, successful dispatch still marks sent, and the response reflects failures without broad behavioral drift.
Risk level: medium-low, backend-only, localized to reminders run path.
PR mode: draft PR only after tests pass and the diff is reviewable; keep the claim to failed-delivery handling, not full retry architecture.

Verification note: backend tests now run against a fake Redis fixture in `tests/conftest.py`, so the reminder/auth paths are reproducible without a live Redis daemon in this workspace.
