#!/usr/bin/env python3
import sys

with open('packages/backend/app/db/schema.sql', 'r') as f:
    lines = f.readlines()

# Find lines matching the enum pattern
target_start = "DO $$ BEGIN\n"
target_cont = "  CREATE TYPE account_type AS ENUM ('BANK', 'CREDIT_CARD', 'INVESTMENT', 'CASH', 'OTHER');\n"
target_except = "EXCEPTION\n"
target_when = "  WHEN duplicate_object THEN NULL;\n"
target_end = "END $$;\n"
# We'll iterate and count occurrences.
new_lines = []
i = 0
occurrence = 0
while i < len(lines):
    if lines[i] == target_start and i+4 < len(lines) and lines[i+1] == target_cont and lines[i+2] == target_except and lines[i+3] == target_when and lines[i+4] == target_end:
        occurrence += 1
        if occurrence == 1:
            # keep first
            new_lines.extend(lines[i:i+5])
        else:
            # skip second (duplicate)
            pass
        i += 5
    else:
        new_lines.append(lines[i])
        i += 1

with open('packages/backend/app/db/schema.sql', 'w') as f:
    f.writelines(new_lines)
print("Removed duplicate enum")