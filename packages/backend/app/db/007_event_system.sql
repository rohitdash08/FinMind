-- Migration: Event-Driven Financial Activity System
-- Issue: #97

-- Financial events log (append-only)
CREATE TABLE IF NOT EXISTS financial_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER,
    payload JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_user ON financial_events (user_id);
CREATE INDEX idx_events_type ON financial_events (event_type);
CREATE INDEX idx_events_entity ON financial_events (entity_type, entity_id);
CREATE INDEX idx_events_created ON financial_events (created_at DESC);
CREATE INDEX idx_events_user_type ON financial_events (user_id, event_type);

-- Event subscriptions (webhook-style or internal)
CREATE TABLE IF NOT EXISTS event_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    callback_type VARCHAR(20) NOT NULL DEFAULT 'internal',
    callback_url VARCHAR(500),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (user_id, event_type, callback_type)
);

CREATE INDEX idx_subscriptions_user ON event_subscriptions (user_id, is_active);
