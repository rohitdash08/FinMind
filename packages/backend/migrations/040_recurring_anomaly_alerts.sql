-- Migration 040: Recurring transaction anomaly alerts
-- Tracks expected amounts, detects deviations, generates alerts

CREATE TABLE IF NOT EXISTS recurring_expense_snapshots (
    id SERIAL PRIMARY KEY,
    recurring_id INTEGER NOT NULL REFERENCES recurring_expenses(id) ON DELETE CASCADE,
    amount NUMERIC(12, 2) NOT NULL,
    recorded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recurring_anomaly_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recurring_id INTEGER NOT NULL REFERENCES recurring_expenses(id) ON DELETE CASCADE,
    expected_amount NUMERIC(12, 2) NOT NULL,
    actual_amount NUMERIC(12, 2) NOT NULL,
    deviation_pct NUMERIC(8, 2) NOT NULL,
    alert_type VARCHAR(30) NOT NULL DEFAULT 'amount_change',
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_snapshots_recurring ON recurring_expense_snapshots(recurring_id);
CREATE INDEX idx_snapshots_recorded ON recurring_expense_snapshots(recorded_at);
CREATE INDEX idx_anomaly_alerts_user ON recurring_anomaly_alerts(user_id);
CREATE INDEX idx_anomaly_alerts_ack ON recurring_anomaly_alerts(user_id, acknowledged);
CREATE INDEX idx_anomaly_alerts_recurring ON recurring_anomaly_alerts(recurring_id);
