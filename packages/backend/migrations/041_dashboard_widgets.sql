-- Migration 041: Customizable dashboard widgets
-- Allows users to show/hide and reorder dashboard sections

CREATE TABLE IF NOT EXISTS dashboard_widgets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    widget_key VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    visible BOOLEAN DEFAULT TRUE,
    position INTEGER NOT NULL DEFAULT 0,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, widget_key)
);

CREATE INDEX idx_widgets_user ON dashboard_widgets(user_id);
CREATE INDEX idx_widgets_position ON dashboard_widgets(user_id, position);
