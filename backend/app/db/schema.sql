CREATE TABLE savings_goals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    target_amount NUMERIC NOT NULL,
    current_amount NUMERIC DEFAULT 0.0,
    description VARCHAR(255),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE milestones (
    id SERIAL PRIMARY KEY,
    savings_goal_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    amount NUMERIC NOT NULL,
    description VARCHAR(255),
    FOREIGN KEY (savings_goal_id) REFERENCES savings_goals(id)
);

ALTER TABLE users ADD COLUMN savings_goals JSONB DEFAULT '[]';
ALTER TABLE users ADD COLUMN milestones JSONB DEFAULT '[]';

-- Indexes for faster lookups
CREATE INDEX idx_savings_goals_user_id ON savings_goals(user_id);
CREATE INDEX idx_milestones_savings_goal_id ON milestones(savings_goal_id);