-- Migration: Lifestyle inflation detection insights
-- Issue #118

CREATE TABLE IF NOT EXISTS lifestyle_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    total_spending DECIMAL(12,2) NOT NULL DEFAULT 0,
    category_spending JSONB DEFAULT '{}',
    transaction_count INTEGER DEFAULT 0,
    avg_transaction DECIMAL(12,2) DEFAULT 0,
    top_categories JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inflation_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id),
    category_name VARCHAR(100),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) DEFAULT 'moderate',
    current_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    previous_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    change_pct DECIMAL(8,2) DEFAULT 0,
    message TEXT NOT NULL,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_snapshots_user_id ON lifestyle_snapshots(user_id);
CREATE INDEX idx_snapshots_period ON lifestyle_snapshots(period_start, period_end);
CREATE INDEX idx_inflation_alerts_user_id ON inflation_alerts(user_id);
CREATE INDEX idx_inflation_alerts_type ON inflation_alerts(alert_type);
CREATE INDEX idx_inflation_alerts_severity ON inflation_alerts(severity);
