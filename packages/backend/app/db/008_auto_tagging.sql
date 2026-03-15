-- Migration: Rule-based Auto Tagging & Categorization
-- Issue: #107

-- Tagging rules table
CREATE TABLE IF NOT EXISTS tagging_rules (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    -- Match conditions (all are optional, combined with AND)
    match_field VARCHAR(20) NOT NULL DEFAULT 'notes',
    match_pattern VARCHAR(500) NOT NULL,
    match_type VARCHAR(20) NOT NULL DEFAULT 'contains',
    min_amount NUMERIC(12, 2),
    max_amount NUMERIC(12, 2),
    currency VARCHAR(10),
    -- Actions
    assign_category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    assign_tags VARCHAR(500),
    -- Metadata
    priority INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    auto_apply BOOLEAN NOT NULL DEFAULT TRUE,
    applied_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tagging_rules_user ON tagging_rules (user_id, is_active);
CREATE INDEX idx_tagging_rules_priority ON tagging_rules (user_id, priority DESC);

-- Tags on expenses (many-to-many via JSON or separate table)
-- Using a simple tags column on expenses for simplicity
-- ALTER TABLE expenses ADD COLUMN IF NOT EXISTS tags VARCHAR(500);
