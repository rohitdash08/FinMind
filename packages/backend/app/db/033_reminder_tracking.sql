-- Migration: Reminder reliability tracking
-- Track delivery status and metrics for reminders

CREATE TABLE IF NOT EXISTS reminder_deliveries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id     INTEGER NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel         VARCHAR(20)  NOT NULL DEFAULT 'email',  -- email, push, sms, in_app
    status          VARCHAR(20)  NOT NULL DEFAULT 'pending', -- pending, sent, delivered, failed, bounced
    attempt_number  INTEGER      DEFAULT 1,
    sent_at         TIMESTAMP,
    delivered_at    TIMESTAMP,
    failed_at       TIMESTAMP,
    failure_reason  VARCHAR(256),
    response_code   VARCHAR(10),
    latency_ms      INTEGER,     -- delivery latency in milliseconds
    opened          BOOLEAN      DEFAULT FALSE,
    opened_at       TIMESTAMP,
    clicked         BOOLEAN      DEFAULT FALSE,
    clicked_at      TIMESTAMP,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reminder_deliveries_reminder ON reminder_deliveries(reminder_id);
CREATE INDEX idx_reminder_deliveries_user     ON reminder_deliveries(user_id, created_at);
CREATE INDEX idx_reminder_deliveries_status   ON reminder_deliveries(status);
