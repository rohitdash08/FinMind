CREATE TABLE IF NOT EXISTS background_jobs (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id) ON DELETE SET NULL,
  job_type VARCHAR(100) NOT NULL,
  payload TEXT,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  attempt INT NOT NULL DEFAULT 0,
  max_retries INT NOT NULL DEFAULT 3,
  retry_backoff_seconds INT NOT NULL DEFAULT 60,
  last_error TEXT,
  scheduled_at TIMESTAMP NOT NULL,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_background_jobs_status ON background_jobs(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_background_jobs_user ON background_jobs(user_id);
