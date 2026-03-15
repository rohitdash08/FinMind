-- Migration: Category overspend early warning system
-- Issue: #117
-- Enables budget limits per category with configurable alert thresholds

CREATE TABLE IF NOT EXISTS category_budgets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    monthly_limit NUMERIC(12,2) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    warning_threshold NUMERIC(5,2) NOT NULL DEFAULT 80.00,
    critical_threshold NUMERIC(5,2) NOT NULL DEFAULT 95.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_category_budget UNIQUE (user_id, category_id)
);

CREATE TABLE IF NOT EXISTS overspend_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    budget_id INTEGER NOT NULL REFERENCES category_budgets(id) ON DELETE CASCADE,
    alert_type VARCHAR(20) NOT NULL DEFAULT 'warning',
    spent_amount NUMERIC(12,2) NOT NULL,
    budget_limit NUMERIC(12,2) NOT NULL,
    percentage_used NUMERIC(6,2) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cat_budgets_user ON category_budgets(user_id);
CREATE INDEX IF NOT EXISTS idx_cat_budgets_active ON category_budgets(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_overspend_alerts_user ON overspend_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_overspend_alerts_unread ON overspend_alerts(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_overspend_alerts_period ON overspend_alerts(period_start, period_end);
