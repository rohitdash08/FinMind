-- Migration: Login Anomaly Detection Tables
-- Creates login_events and security_alerts tables for tracking
-- suspicious login activities and generating security alerts.

-- Login Events Table
-- Tracks all login-related events including successful logins,
-- failed attempts, and suspicious activities.
CREATE TABLE IF NOT EXISTS login_events (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(30) NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    device_fingerprint VARCHAR(128),
    location_country VARCHAR(100),
    location_city VARCHAR(100),
    risk_score NUMERIC(3,2) NOT NULL DEFAULT 0.0,
    risk_factors TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index for quick lookup of user's recent login events
CREATE INDEX IF NOT EXISTS idx_login_events_user_created 
    ON login_events(user_id, created_at DESC);

-- Index for IP-based queries (detecting same IP across accounts)
CREATE INDEX IF NOT EXISTS idx_login_events_ip 
    ON login_events(ip_address, created_at DESC);

-- Index for event type filtering
CREATE INDEX IF NOT EXISTS idx_login_events_type 
    ON login_events(event_type, created_at DESC);

-- Security Alerts Table
-- Stores security alerts generated from suspicious activities
CREATE TABLE IF NOT EXISTS security_alerts (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    title VARCHAR(200) NOT NULL,
    description TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    login_event_id INT REFERENCES login_events(id) ON DELETE SET NULL,
    acknowledged_at TIMESTAMP,
    acknowledged_by INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index for user's alerts lookup
CREATE INDEX IF NOT EXISTS idx_security_alerts_user_status 
    ON security_alerts(user_id, status, created_at DESC);

-- Index for alert type filtering
CREATE INDEX IF NOT EXISTS idx_security_alerts_type 
    ON security_alerts(alert_type, created_at DESC);

-- Index for severity filtering
CREATE INDEX IF NOT EXISTS idx_security_alerts_severity 
    ON security_alerts(severity, created_at DESC);

-- Extend audit_logs table with additional columns for login events
ALTER TABLE audit_logs 
    ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45);

ALTER TABLE audit_logs 
    ADD COLUMN IF NOT EXISTS details TEXT;

-- Add comment for documentation
COMMENT ON TABLE login_events IS 'Tracks all login events for anomaly detection';
COMMENT ON TABLE security_alerts IS 'Security alerts generated from suspicious activities';
COMMENT ON COLUMN login_events.risk_score IS 'Risk score from 0.0 (safe) to 1.0 (high risk)';
COMMENT ON COLUMN login_events.risk_factors IS 'JSON array of detected risk factors';