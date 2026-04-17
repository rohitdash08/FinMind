-- FinMind Savings Goals Database Schema
DO $$ BEGIN
    CREATE TYPE goal_status AS ENUM ('active', 'completed', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS savings_goals (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    target_amount NUMERIC(12, 2) NOT NULL CHECK (target_amount > 0),
    current_amount NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (current_amount >= 0),
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    deadline DATE,
    status goal_status NOT NULL DEFAULT 'active',
    description VARCHAR(500),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_savings_goals_user_status ON savings_goals(user_id, status);
CREATE INDEX IF NOT EXISTS idx_savings_goals_user_deadline ON savings_goals(user_id, deadline);

CREATE TABLE IF NOT EXISTS savings_contributions (
    id SERIAL PRIMARY KEY,
    goal_id INT NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency VARCHAR(10) NOT NULL DEFAULT 'INR',
    note VARCHAR(500),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contributions_goal_created ON savings_contributions(goal_id, created_at DESC);

CREATE TABLE IF NOT EXISTS savings_milestones (
    id SERIAL PRIMARY KEY,
    goal_id INT NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
    percentage INT NOT NULL CHECK (percentage IN (25, 50, 75, 100)),
    achieved_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_milestones_goal_pct ON savings_milestones(goal_id, percentage);
