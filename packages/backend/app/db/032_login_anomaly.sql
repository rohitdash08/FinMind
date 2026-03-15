-- Migration: Login anomaly detection
-- Tracks login events and suspicious activity alerts

CREATE TABLE IF NOT EXISTS login_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type      VARCHAR(20) NOT NULL DEFAULT 'login',  -- login, failed_login, logout
    ip_address      VARCHAR(45),
    user_agent      VARCHAR(512),
    device_type     VARCHAR(20),
    browser         VARCHAR(64),
    os              VARCHAR(64),
    location        VARCHAR(128),
    country_code    VARCHAR(5),
    is_suspicious   BOOLEAN DEFAULT FALSE,
    risk_score      REAL    DEFAULT 0.0,        -- 0.0-1.0
    anomaly_reasons TEXT,                       -- JSON array of reason strings
    session_id      VARCHAR(64),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_type      VARCHAR(50) NOT NULL,       -- new_device, unusual_location, rapid_attempts, etc.
    severity        VARCHAR(20) DEFAULT 'medium', -- low, medium, high, critical
    title           VARCHAR(256) NOT NULL,
    description     TEXT,
    metadata        TEXT,                        -- JSON with alert-specific data
    acknowledged    BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_login_events_user    ON login_events(user_id, created_at);
CREATE INDEX idx_login_events_ip      ON login_events(ip_address);
CREATE INDEX idx_security_alerts_user ON security_alerts(user_id, created_at);
