#!/usr/bin/env python3
import sys

with open('packages/backend/app/models.py', 'r') as f:
    lines = f.readlines()

# Find line numbers for Category class and Expense class
cat_start = -1
exp_start = -1
for i, line in enumerate(lines):
    if line.strip().startswith('class Category(db.Model):'):
        cat_start = i
    if line.strip().startswith('class Expense(db.Model):'):
        exp_start = i
        break

if cat_start == -1 or exp_start == -1:
    print("Could not find classes")
    sys.exit(1)

# Insert after Category class, before Expense class
# We'll insert after the closing line of Category (the line after the class definition)
# Find the line after the class block (indentation level 0)
# Simple: insert at exp_start (just before Expense class)
insert_idx = exp_start

# New enum and model
new_lines = [
    '\n',
    'class AccountType(str, Enum):\n',
    '    BANK = "BANK"\n',
    '    CREDIT_CARD = "CREDIT_CARD"\n',
    '    INVESTMENT = "INVESTMENT"\n',
    '    CASH = "CASH"\n',
    '    OTHER = "OTHER"\n',
    '\n',
    '\n',
    'class FinancialAccount(db.Model):\n',
    '    __tablename__ = "financial_accounts"\n',
    '    id = db.Column(db.Integer, primary_key=True)\n',
    '    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)\n',
    '    name = db.Column(db.String(100), nullable=False)\n',
    '    type = db.Column(SAEnum(AccountType), default=AccountType.BANK, nullable=False)\n',
    '    currency = db.Column(db.String(10), default="INR", nullable=False)\n',
    '    balance = db.Column(db.Numeric(12, 2), nullable=True)\n',
    '    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)\n',
    '\n',
    '\n',
]

# Insert them
lines[insert_idx:insert_idx] = new_lines

# Now add account_id foreign key columns to Expense, RecurringExpense, Bill
# We need to locate each class and add column after user_id or category_id.
# Let's find Expense class start and add column after category_id (or after source_recurring_id?)
# We'll add after source_recurring_id line.
# We'll search for 'source_recurring_id = db.Column(' line and insert after that line.
for i, line in enumerate(lines):
    if 'source_recurring_id = db.Column(' in line:
        # Insert account_id line after this line (i+1)
        lines.insert(i+1, '    account_id = db.Column(db.Integer, db.ForeignKey("financial_accounts.id"), nullable=True)\n')
        break

# Find RecurringExpense class and add after category_id line
for i, line in enumerate(lines):
    if 'class RecurringExpense(db.Model):' in line:
        # find the line with 'category_id = db.Column(' after this class
        for j in range(i, len(lines)):
            if 'category_id = db.Column(' in lines[j]:
                lines.insert(j+1, '    account_id = db.Column(db.Integer, db.ForeignKey("financial_accounts.id"), nullable=True)\n')
                break
        break

# Find Bill class and add after user_id line (or before name)
for i, line in enumerate(lines):
    if 'class Bill(db.Model):' in line:
        for j in range(i, len(lines)):
            if 'name = db.Column(' in lines[j]:
                # insert before name line
                lines.insert(j, '    account_id = db.Column(db.Integer, db.ForeignKey("financial_accounts.id"), nullable=True)\n')
                break
        break

# Write back
with open('packages/backend/app/models.py', 'w') as f:
    f.writelines(lines)

print("Models updated")