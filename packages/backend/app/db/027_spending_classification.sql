-- Essential vs Discretionary Spending Classification
-- Adds spending_class column to categories for classification

ALTER TABLE categories
ADD COLUMN spending_class VARCHAR(20) DEFAULT 'UNCLASSIFIED' NOT NULL;

-- Default essential categories (users can reclassify)
-- These would be applied via the API, not in migration
-- Common essential: Housing, Utilities, Groceries, Healthcare, Insurance, Transport
-- Common discretionary: Dining Out, Entertainment, Shopping, Travel, Subscriptions
