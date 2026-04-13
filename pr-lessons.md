# PR Lessons

- Keep claims narrow and prove them with one failing-mode regression test.
- For backend scheduling/reminder work, dedup and idempotency are the maintainer-friendly proof points.
- Reminder dispatch should never mark a reminder sent on failed delivery, because that hides unrecoverable state and makes retry proofs weaker.
