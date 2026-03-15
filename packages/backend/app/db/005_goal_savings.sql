-- Migration: Goal-based savings tracking & milestones
-- Adds tables for savings goals, contributions, and milestone tracking.

DO $$ BEGIN
  CREATE TYPE goal_status AS ENUM ('ACTIVE', 'PAUSED', 'COMPLETED', 'CANCELLED');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS savings_goals (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(200) NOT NULL,
  target_amount NUMERIC(12,2) NOT NULL,
  current_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
  currency VARCHAR(10) NOT NULL DEFAULT 'INR',
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  target_date DATE,
  icon VARCHAR(50) DEFAULT 'piggy-bank',
  color VARCHAR(7) DEFAULT '#4F46E5',
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_savings_goals_user ON savings_goals(user_id, status);

CREATE TABLE IF NOT EXISTS goal_contributions (
  id SERIAL PRIMARY KEY,
  goal_id INT NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  amount NUMERIC(12,2) NOT NULL,
  notes VARCHAR(500),
  contributed_at DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_goal_contributions_goal ON goal_contributions(goal_id);

CREATE TABLE IF NOT EXISTS goal_milestones (
  id SERIAL PRIMARY KEY,
  goal_id INT NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
  percentage INT NOT NULL,
  title VARCHAR(200) NOT NULL,
  reached_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_goal_milestones_goal ON goal_milestones(goal_id, percentage);
