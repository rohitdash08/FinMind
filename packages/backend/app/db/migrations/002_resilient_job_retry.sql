-- Migration 002: Resilient background job retry & monitoring
-- Issue #130
-- Apply with: psql $DATABASE_URL -f migrations/002_resilient_job_retry.sql

-- Retry fields on reminders
ALTER TABLE reminders
    ADD COLUMN IF NOT EXISTS retry_count       INTEGER     NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS max_retries       INTEGER     NOT NULL DEFAULT 3,
    ADD COLUMN IF NOT EXISTS next_retry_at     TIMESTAMP   NULL,
    ADD COLUMN IF NOT EXISTS last_error        VARCHAR(500) NULL,
    ADD COLUMN IF NOT EXISTS failed_permanently BOOLEAN    NOT NULL DEFAULT FALSE;

-- Index to efficiently query pending/retryable reminders
CREATE INDEX IF NOT EXISTS idx_reminders_pending
    ON reminders (sent, failed_permanently, next_retry_at)
    WHERE sent = FALSE AND failed_permanently = FALSE;

-- Job run audit table
CREATE TABLE IF NOT EXISTS job_runs (
    id           SERIAL PRIMARY KEY,
    job_name     VARCHAR(100)  NOT NULL,
    started_at   TIMESTAMP     NOT NULL DEFAULT NOW(),
    finished_at  TIMESTAMP     NULL,
    status       VARCHAR(20)   NOT NULL,   -- success | partial | failed | running
    processed    INTEGER       NOT NULL DEFAULT 0,
    succeeded    INTEGER       NOT NULL DEFAULT 0,
    errors       INTEGER       NOT NULL DEFAULT 0,
    retried      INTEGER       NOT NULL DEFAULT 0,
    details      TEXT          NULL
);

CREATE INDEX IF NOT EXISTS idx_job_runs_name_started
    ON job_runs (job_name, started_at DESC);
