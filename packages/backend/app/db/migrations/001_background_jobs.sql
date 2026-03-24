-- Background job tracking for resilient retry & monitoring
-- Part of: Resilient background job retry & monitoring (Issue #130)

DO $$ BEGIN
  CREATE TYPE job_status AS ENUM ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'DEAD_LETTER');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS background_jobs (
  id SERIAL PRIMARY KEY,
  job_type VARCHAR(100) NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  status job_status NOT NULL DEFAULT 'PENDING',
  attempt INT NOT NULL DEFAULT 0,
  max_retries INT NOT NULL DEFAULT 3,
  next_run_at TIMESTAMP NOT NULL DEFAULT NOW(),
  last_error TEXT,
  result JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bg_jobs_status_next_run ON background_jobs(status, next_run_at);
CREATE INDEX IF NOT EXISTS idx_bg_jobs_type ON background_jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_bg_jobs_created ON background_jobs(created_at DESC);
