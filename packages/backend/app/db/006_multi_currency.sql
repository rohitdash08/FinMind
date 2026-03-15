-- Migration: Multi-Currency & FX Conversion Support
-- Issue: #95

-- Exchange rates cache table
CREATE TABLE IF NOT EXISTS exchange_rates (
    id SERIAL PRIMARY KEY,
    base_currency VARCHAR(10) NOT NULL,
    target_currency VARCHAR(10) NOT NULL,
    rate NUMERIC(18, 8) NOT NULL,
    rate_date DATE NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'manual',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (base_currency, target_currency, rate_date)
);

CREATE INDEX idx_exchange_rates_pair ON exchange_rates (base_currency, target_currency);
CREATE INDEX idx_exchange_rates_date ON exchange_rates (rate_date DESC);

-- Supported currencies reference table
CREATE TABLE IF NOT EXISTS supported_currencies (
    code VARCHAR(10) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    decimal_places INTEGER NOT NULL DEFAULT 2,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Seed common currencies
INSERT INTO supported_currencies (code, name, symbol, decimal_places) VALUES
    ('USD', 'US Dollar', '$', 2),
    ('EUR', 'Euro', '€', 2),
    ('GBP', 'British Pound', '£', 2),
    ('INR', 'Indian Rupee', '₹', 2),
    ('JPY', 'Japanese Yen', '¥', 0),
    ('CAD', 'Canadian Dollar', 'CA$', 2),
    ('AUD', 'Australian Dollar', 'A$', 2),
    ('CHF', 'Swiss Franc', 'CHF', 2),
    ('CNY', 'Chinese Yuan', '¥', 2),
    ('SGD', 'Singapore Dollar', 'S$', 2),
    ('HKD', 'Hong Kong Dollar', 'HK$', 2),
    ('KRW', 'South Korean Won', '₩', 0),
    ('BRL', 'Brazilian Real', 'R$', 2),
    ('MXN', 'Mexican Peso', 'MX$', 2),
    ('ZAR', 'South African Rand', 'R', 2)
ON CONFLICT (code) DO NOTHING;
