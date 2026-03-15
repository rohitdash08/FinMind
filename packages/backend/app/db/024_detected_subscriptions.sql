-- Migration: Auto-detect subscriptions from recurring charges
-- Issue: #109
-- Detects subscription services by analyzing recurring transaction patterns

CREATE TABLE IF NOT EXISTS detected_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    merchant_name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    cadence VARCHAR(20) NOT NULL DEFAULT 'MONTHLY',
    confidence NUMERIC(5,4) NOT NULL DEFAULT 0.0,
    first_seen DATE NOT NULL,
    last_seen DATE NOT NULL,
    next_expected DATE,
    occurrence_count INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'detected',
    linked_recurring_id INTEGER REFERENCES recurring_expenses(id),
    category_id INTEGER REFERENCES categories(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_merchant_cadence UNIQUE (user_id, normalized_name, cadence)
);

CREATE INDEX IF NOT EXISTS idx_detected_subs_user ON detected_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_detected_subs_status ON detected_subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_detected_subs_active ON detected_subscriptions(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_detected_subs_next ON detected_subscriptions(next_expected);
