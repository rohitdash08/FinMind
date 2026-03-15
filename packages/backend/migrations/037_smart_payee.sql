-- Migration: Smart Payee & Merchant Alias Management
-- Closes #114

CREATE TABLE IF NOT EXISTS merchants (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    normalized_name VARCHAR(200) NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    default_currency VARCHAR(10) DEFAULT 'INR',
    notes TEXT,
    transaction_count INTEGER DEFAULT 0,
    total_spent NUMERIC(14, 2) DEFAULT 0,
    last_transaction_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, normalized_name)
);

CREATE TABLE IF NOT EXISTS merchant_aliases (
    id SERIAL PRIMARY KEY,
    merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    alias VARCHAR(200) NOT NULL,
    normalized_alias VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(merchant_id, normalized_alias)
);

CREATE INDEX idx_merchants_user_id ON merchants(user_id);
CREATE INDEX idx_merchants_normalized_name ON merchants(user_id, normalized_name);
CREATE INDEX idx_merchant_aliases_merchant_id ON merchant_aliases(merchant_id);
CREATE INDEX idx_merchant_aliases_normalized ON merchant_aliases(normalized_alias);
