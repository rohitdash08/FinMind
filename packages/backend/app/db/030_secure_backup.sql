-- Migration: Secure backup & encrypted export
-- Issue: #126

CREATE TABLE IF NOT EXISTS backup_records (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    backup_type VARCHAR(20) NOT NULL DEFAULT 'full',
    format VARCHAR(10) NOT NULL DEFAULT 'json',
    encrypted BOOLEAN NOT NULL DEFAULT true,
    file_hash VARCHAR(128),
    file_size INTEGER,
    record_count INTEGER DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE INDEX idx_backup_records_user ON backup_records(user_id);
CREATE INDEX idx_backup_records_status ON backup_records(status);
