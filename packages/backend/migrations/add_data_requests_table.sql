-- Migration: Add data_requests table for PII Export & Delete (Issue #76)
CREATE TABLE IF NOT EXISTS data_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    request_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    confirmation_token VARCHAR(64),
    token_expires_at TIMESTAMP,
    package_path TEXT,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata_json TEXT
);

CREATE INDEX idx_data_requests_user_id ON data_requests(user_id);
CREATE INDEX idx_data_requests_token ON data_requests(confirmation_token);
