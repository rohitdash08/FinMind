#!/usr/bin/env python3
import sys

with open('packages/backend/app/db/schema.sql', 'r') as f:
    content = f.read()

# Insert account_type enum after bill_cadence enum
target = """DO $$ BEGIN
  CREATE TYPE bill_cadence AS ENUM ('MONTHLY','WEEKLY','YEARLY','ONCE');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;"""
new_enum = """DO $$ BEGIN
  CREATE TYPE account_type AS ENUM ('BANK', 'CREDIT_CARD', 'INVESTMENT', 'CASH', 'OTHER');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;"""

if target not in content:
    print("Target not found")
    sys.exit(1)

# Insert after target, before next line
parts = content.split(target, 1)
new_content = parts[0] + target + '\n\n' + new_enum + parts[1]

# Now insert financial_accounts table after categories table (or after the new enum?)
# Let's insert after the categories CREATE TABLE block and before expenses block.
# We'll find the line "CREATE TABLE IF NOT EXISTS expenses"
expenses_pos = new_content.find('CREATE TABLE IF NOT EXISTS expenses')
# Find the preceding newline
prev_newline = new_content.rfind('\n', 0, expenses_pos)
# Insert after that newline (so before expenses)
insert_pos = prev_newline
account_table = """
DO $$ BEGIN
  CREATE TYPE account_type AS ENUM ('BANK', 'CREDIT_CARD', 'INVESTMENT', 'CASH', 'OTHER');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS financial_accounts (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(100) NOT NULL,
  type account_type NOT NULL DEFAULT 'BANK',
  currency VARCHAR(10) NOT NULL DEFAULT 'INR',
  balance NUMERIC(12,2) DEFAULT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_financial_accounts_user ON financial_accounts(user_id);
"""
# But we already added enum above, we need to avoid duplicate enum.
# Let's just insert the table after categories and before expenses.
# Find categories block end.
categories_end = new_content.find('CREATE TABLE IF NOT EXISTS categories')
if categories_end == -1:
    print("Categories not found")
    sys.exit(1)
# Find the closing parenthesis and semicolon after categories.
cat_end = new_content.find(');', categories_end) + 2
# Insert after that line.
# Ensure we have a newline.
new_content = new_content[:cat_end] + '\n\n' + account_table + new_content[cat_end:]

# Now add account_id columns to expenses, recurring_expenses, bills
# We'll add ALTER statements after the CREATE TABLE for each respective table.
# Let's add after each CREATE TABLE block, but easier: add ALTER statements at the end of the file before the last line.
# Find the last line (empty line?) We'll append before the file ends.
# Let's add after all CREATE TABLE statements but before the end of file.
# We'll insert before the final line (which is empty). We'll add a section.
alter_section = """
ALTER TABLE expenses
  ADD COLUMN IF NOT EXISTS account_id INT REFERENCES financial_accounts(id) ON DELETE SET NULL;
ALTER TABLE recurring_expenses
  ADD COLUMN IF NOT EXISTS account_id INT REFERENCES financial_accounts(id) ON DELETE SET NULL;
ALTER TABLE bills
  ADD COLUMN IF NOT EXISTS account_id INT REFERENCES financial_accounts(id) ON DELETE SET NULL;
"""
# Insert before the last newline.
new_content = new_content.rstrip() + '\n' + alter_section + '\n'

with open('packages/backend/app/db/schema.sql', 'w') as f:
    f.write(new_content)
print("Schema updated")