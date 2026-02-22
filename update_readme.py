#!/usr/bin/env python3
import sys

with open('README.md', 'r') as f:
    lines = f.readlines()

# Find the line with "API Endpoints"
api_start = -1
for i, line in enumerate(lines):
    if line.strip() == '## API Endpoints':
        api_start = i
        break

if api_start == -1:
    print("API Endpoints section not found")
    sys.exit(1)

# Find the next heading after that (line starting with "##")
next_heading = -1
for i in range(api_start + 1, len(lines)):
    if lines[i].startswith('##'):
        next_heading = i
        break
if next_heading == -1:
    next_heading = len(lines)

# Insert before next_heading
new_lines = [
    '- Dashboard: `/dashboard/summary?month=YYYY-MM&account_id=<id>` – overview for a specific financial account (or all accounts if omitted).\n',
    '- Financial Accounts: CRUD at `/accounts` (list, create, update, delete).\n'
]
lines[next_heading:next_heading] = new_lines

# Also add a new section for Financial Accounts after the API Endpoints? Let's add after the MVP UI/UX Plan maybe.
# Let's just add a new heading "Multi-Account Financial Overview" after the API Endpoints section.
# We'll insert after the bullet list (before next heading). We'll need to find where the bullet list ends.
# For simplicity, add after the inserted bullets.
# Let's also add a note about schema changes.
# We'll just keep it simple.

with open('README.md', 'w') as f:
    f.writelines(lines)

print("README updated")