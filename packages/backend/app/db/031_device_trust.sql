-- Migration: Device trust management
-- Adds trusted_devices table for device recognition and management

CREATE TABLE IF NOT EXISTS trusted_devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id       VARCHAR(64)  NOT NULL,           -- unique device fingerprint
    device_name     VARCHAR(128),                     -- user-friendly name
    device_type     VARCHAR(20)  DEFAULT 'unknown',  -- mobile, desktop, tablet, unknown
    browser         VARCHAR(64),                      -- browser name
    os              VARCHAR(64),                      -- operating system
    ip_address      VARCHAR(45),                      -- last known IP (IPv4/IPv6)
    location        VARCHAR(128),                     -- approximate location
    trust_level     VARCHAR(20)  DEFAULT 'standard',  -- full, standard, limited
    is_current      BOOLEAN      DEFAULT FALSE,
    last_active_at  TIMESTAMP,
    trusted_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP,
    revoked         BOOLEAN      DEFAULT FALSE,
    revoked_at      TIMESTAMP,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trusted_devices_user   ON trusted_devices(user_id);
CREATE INDEX idx_trusted_devices_device ON trusted_devices(user_id, device_id);
