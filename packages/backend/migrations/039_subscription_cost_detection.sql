-- Migration 039: Subscription cost increase detection
-- Tracks price history for subscription plans and alerts on increases

CREATE TABLE IF NOT EXISTS subscription_price_history (
    id SERIAL PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES subscription_plans(id) ON DELETE CASCADE,
    old_price_cents INTEGER NOT NULL,
    new_price_cents INTEGER NOT NULL,
    change_pct NUMERIC(8, 2) NOT NULL,
    detected_at TIMESTAMP DEFAULT NOW(),
    notified BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS subscription_cost_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id INTEGER NOT NULL REFERENCES subscription_plans(id) ON DELETE CASCADE,
    old_price_cents INTEGER NOT NULL,
    new_price_cents INTEGER NOT NULL,
    change_pct NUMERIC(8, 2) NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_price_history_plan ON subscription_price_history(plan_id);
CREATE INDEX idx_price_history_detected ON subscription_price_history(detected_at);
CREATE INDEX idx_cost_alerts_user ON subscription_cost_alerts(user_id);
CREATE INDEX idx_cost_alerts_ack ON subscription_cost_alerts(user_id, acknowledged);
