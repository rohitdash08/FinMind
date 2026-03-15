-- Migration: GDPR PII Export & Delete Workflow
-- Creates tables for tracking data export requests, deletion requests,
-- and GDPR-specific audit trail (immutable, exempt from user deletion).

DO $$ BEGIN
  CREATE TYPE gdpr_action AS ENUM (
    'EXPORT_REQUESTED',
    'EXPORT_COMPLETED',
    'EXPORT_DOWNLOADED',
    'DELETION_REQUESTED',
    'DELETION_CONFIRMED',
    'DELETION_CANCELLED',
    'DELETION_COMPLETED',
    'DELETION_FAILED'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE deletion_status AS ENUM (
    'PENDING',
    'CONFIRMED',
    'PROCESSING',
    'COMPLETED',
    'CANCELLED',
    'FAILED'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- GDPR audit trail: immutable, never deleted even when user is removed
CREATE TABLE IF NOT EXISTS gdpr_audit_logs (
  id SERIAL PRIMARY KEY,
  user_id INT,  -- nullable: user row may be deleted
  user_email VARCHAR(255) NOT NULL,  -- preserved for compliance
  action gdpr_action NOT NULL,
  details JSONB DEFAULT '{}',
  ip_address VARCHAR(45),
  user_agent VARCHAR(500),
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gdpr_audit_user ON gdpr_audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_gdpr_audit_action ON gdpr_audit_logs(action);

-- Deletion requests: tracks the lifecycle of account deletion
CREATE TABLE IF NOT EXISTS deletion_requests (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id),
  status deletion_status NOT NULL DEFAULT 'PENDING',
  reason VARCHAR(500),
  confirmation_token VARCHAR(100) UNIQUE,
  confirmed_at TIMESTAMP,
  grace_period_ends_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_deletion_requests_user ON deletion_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_deletion_requests_status ON deletion_requests(status);

-- Track when user is soft-deleted
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
