-- Migration 010: Webhook Event System
-- Issue #77
-- Apply with: psql $DATABASE_URL -f migrations/010_webhooks.sql

-- Webhook endpoint registrations
CREATE TABLE IF NOT EXISTS webhooks (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url         VARCHAR(2048) NOT NULL,
    secret      VARCHAR(256)  NOT NULL,  -- HMAC signing secret (stored hashed in prod)
    events      JSONB         NOT NULL DEFAULT '[]',  -- list of subscribed event types
    active      BOOLEAN       NOT NULL DEFAULT TRUE,
    description VARCHAR(255)  NULL,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhooks_user ON webhooks (user_id, active);

-- Delivery log: one row per delivery attempt
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id              SERIAL PRIMARY KEY,
    webhook_id      INTEGER       NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event_type      VARCHAR(100)  NOT NULL,
    payload         JSONB         NOT NULL,
    attempt         SMALLINT      NOT NULL DEFAULT 1,
    status          VARCHAR(20)   NOT NULL DEFAULT 'pending',  -- pending|success|failed
    response_code   SMALLINT      NULL,
    response_body   TEXT          NULL,
    error_message   TEXT          NULL,
    delivered_at    TIMESTAMPTZ   NULL,
    next_retry_at   TIMESTAMPTZ   NULL,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook ON webhook_deliveries (webhook_id, status);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_retry   ON webhook_deliveries (next_retry_at)
    WHERE status = 'failed';
