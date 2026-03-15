-- Migration: Add resilient job retry columns to reminders table
-- Issue: #130 — Resilient background job retry & monitoring

ALTER TABLE reminders ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE reminders ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE reminders ADD COLUMN IF NOT EXISTS max_retries INTEGER NOT NULL DEFAULT 3;
ALTER TABLE reminders ADD COLUMN IF NOT EXISTS last_error VARCHAR(500);
ALTER TABLE reminders ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP;
ALTER TABLE reminders ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;
ALTER TABLE reminders ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

-- Backfill: mark already-sent reminders as "sent" status
UPDATE reminders SET status = 'sent' WHERE sent = true AND status = 'pending';

-- Index for efficient due-reminder queries
CREATE INDEX IF NOT EXISTS idx_reminders_status_send_at
    ON reminders (status, send_at)
    WHERE status IN ('pending', 'failed');

-- Index for dead-letter listing
CREATE INDEX IF NOT EXISTS idx_reminders_status_dead
    ON reminders (status)
    WHERE status = 'dead';
