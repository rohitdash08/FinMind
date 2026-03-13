-- Migration 004: Goal-based savings tracking & milestones
-- Issue #133
-- Apply with: psql $DATABASE_URL -f migrations/004_savings_goals.sql

CREATE TABLE IF NOT EXISTS savings_goals (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name           VARCHAR(200)  NOT NULL,
    description    VARCHAR(500)  NULL,
    target_amount  NUMERIC(12,2) NOT NULL,
    current_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency       VARCHAR(10)   NOT NULL DEFAULT 'INR',
    target_date    DATE          NULL,
    achieved       BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS savings_milestones (
    id             SERIAL PRIMARY KEY,
    goal_id        INTEGER       NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
    name           VARCHAR(200)  NOT NULL,
    target_amount  NUMERIC(12,2) NOT NULL,
    achieved       BOOLEAN       NOT NULL DEFAULT FALSE,
    achieved_at    TIMESTAMP     NULL,
    created_at     TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_savings_goals_user   ON savings_goals (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_savings_milestones_goal ON savings_milestones (goal_id, target_amount);
