-- Migration: Add background_jobs table for retry and monitoring
-- Created: 2026-03-25
-- Issue: #130 Resilient background job retry & monitoring

CREATE TABLE IF NOT EXISTS background_jobs (
    id SERIAL PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,
    payload JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    priority INTEGER NOT NULL DEFAULT 0,
    
    -- Retry tracking
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    next_retry_at TIMESTAMP,
    last_error TEXT,
    
    -- Timing
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Result
    result JSONB,
    
    -- User association
    user_id INTEGER REFERENCES users(id)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_background_jobs_status ON background_jobs(status);
CREATE INDEX IF NOT EXISTS idx_background_jobs_priority_created ON background_jobs(priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_background_jobs_next_retry ON background_jobs(next_retry_at) WHERE status = 'RETRYING';
CREATE INDEX IF NOT EXISTS idx_background_jobs_user_id ON background_jobs(user_id);

-- Comments for documentation
COMMENT ON TABLE background_jobs IS 'Background jobs with retry and monitoring support';
COMMENT ON COLUMN background_jobs.job_type IS 'Type of job: SEND_REMINDER, SEND_EMAIL, etc.';
COMMENT ON COLUMN background_jobs.status IS 'Job status: PENDING, RUNNING, SUCCEEDED, FAILED, RETRYING, DEAD_LETTER';
COMMENT ON COLUMN background_jobs.priority IS 'Higher priority jobs are processed first';
COMMENT ON COLUMN background_jobs.retry_count IS 'Number of retry attempts made';
COMMENT ON COLUMN background_jobs.max_retries IS 'Maximum retry attempts allowed';
COMMENT ON COLUMN background_jobs.next_retry_at IS 'When to retry this job (for exponential backoff)';
COMMENT ON COLUMN background_jobs.last_error IS 'Error message from last failure';