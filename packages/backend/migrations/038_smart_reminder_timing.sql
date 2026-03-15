-- Migration: Smart Reminder Timing Optimization
-- Closes #111

CREATE TABLE IF NOT EXISTS user_activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    hour_of_day INTEGER NOT NULL CHECK (hour_of_day >= 0 AND hour_of_day <= 23),
    day_of_week INTEGER NOT NULL CHECK (day_of_week >= 0 AND day_of_week <= 6),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reminder_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    preferred_hour INTEGER DEFAULT 9 CHECK (preferred_hour >= 0 AND preferred_hour <= 23),
    preferred_days VARCHAR(50) DEFAULT '1,2,3,4,5',
    quiet_hours_start INTEGER DEFAULT 22 CHECK (quiet_hours_start >= 0 AND quiet_hours_start <= 23),
    quiet_hours_end INTEGER DEFAULT 7 CHECK (quiet_hours_end >= 0 AND quiet_hours_end <= 23),
    auto_optimize BOOLEAN DEFAULT TRUE,
    min_interval_hours INTEGER DEFAULT 4,
    max_reminders_per_day INTEGER DEFAULT 5,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE INDEX idx_activity_logs_user ON user_activity_logs(user_id);
CREATE INDEX idx_activity_logs_hour ON user_activity_logs(user_id, hour_of_day);
CREATE INDEX idx_activity_logs_day ON user_activity_logs(user_id, day_of_week);
CREATE INDEX idx_reminder_prefs_user ON reminder_preferences(user_id);
