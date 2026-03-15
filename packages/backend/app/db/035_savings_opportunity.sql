-- Migration: Savings opportunity detection engine
-- Issue #119

CREATE TABLE IF NOT EXISTS savings_opportunities (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    current_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    target_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    potential_savings DECIMAL(12,2) NOT NULL DEFAULT 0,
    confidence DECIMAL(3,2) DEFAULT 0.5,
    status VARCHAR(20) DEFAULT 'active',
    is_dismissed BOOLEAN DEFAULT FALSE,
    action_taken BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    detected_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_savings_opp_user_id ON savings_opportunities(user_id);
CREATE INDEX idx_savings_opp_type ON savings_opportunities(type);
CREATE INDEX idx_savings_opp_status ON savings_opportunities(status);
CREATE INDEX idx_savings_opp_confidence ON savings_opportunities(confidence);
