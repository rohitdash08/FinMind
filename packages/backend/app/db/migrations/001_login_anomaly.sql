-- Migration: Login Anomaly Detection Tables
-- Issue: #124
-- Date: 2026-03-29

-- Login attempts tracking
CREATE TABLE IF NOT EXISTS login_attempts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    user_agent VARCHAR(500),
    device_fingerprint VARCHAR(64),
    success BOOLEAN NOT NULL DEFAULT FALSE,
    failure_reason VARCHAR(100),
    country VARCHAR(2),
    city VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Known devices for users
CREATE TABLE IF NOT EXISTS user_devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_fingerprint VARCHAR(64) NOT NULL,
    device_name VARCHAR(200),
    ip_address VARCHAR(45) NOT NULL,
    user_agent VARCHAR(500),
    country VARCHAR(2),
    city VARCHAR(100),
    first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_trusted BOOLEAN NOT NULL DEFAULT FALSE,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(user_id, device_fingerprint)
);

-- Login anomalies
CREATE TABLE IF NOT EXISTS login_anomalies (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    login_attempt_id INTEGER REFERENCES login_attempts(id) ON DELETE SET NULL,
    anomaly_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium',
    details TEXT,
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_login_attempts_user_id ON login_attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email);
CREATE INDEX IF NOT EXISTS idx_login_attempts_created_at ON login_attempts(created_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_success ON login_attempts(success);

CREATE INDEX IF NOT EXISTS idx_user_devices_user_id ON user_devices(user_id);
CREATE INDEX IF NOT EXISTS idx_user_devices_fingerprint ON user_devices(device_fingerprint);

CREATE INDEX IF NOT EXISTS idx_login_anomalies_user_id ON login_anomalies(user_id);
CREATE INDEX IF NOT EXISTS idx_login_anomalies_type ON login_anomalies(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_login_anomalies_acknowledged ON login_anomalies(acknowledged);

-- Enum type for anomaly types (PostgreSQL)
DO $$ BEGIN
    CREATE TYPE login_anomaly_type AS ENUM (
        'new_device',
        'new_location', 
        'unusual_time',
        'multiple_failures',
        'suspicious_ip',
        'impossible_travel'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
