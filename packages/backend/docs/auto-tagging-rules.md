# Rule-based Auto Tagging & Categorization

Issue: [#107](https://github.com/rohitdash08/FinMind/issues/107)

## Overview

Flexible rule engine for automatic expense categorization and tagging.
Users define match conditions and actions — rules are applied automatically
to new expenses or bulk-applied to existing uncategorized ones.

## Match Types

| Type | Description | Example |
|------|-------------|---------|
| `contains` | Substring match (case-insensitive) | "uber" matches "Uber ride to office" |
| `exact` | Full string match | "uber" only matches "uber" |
| `starts_with` | Prefix match | "amazon" matches "Amazon Prime" |
| `ends_with` | Suffix match | "coffee" matches "Morning coffee" |
| `regex` | Regular expression | `\d{3,}` matches "Invoice #12345" |

## Match Conditions (combined with AND)

- **Text pattern** — Match against notes field
- **Amount range** — min_amount / max_amount bounds
- **Currency filter** — Only match specific currencies

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tagging/rules` | Create a rule |
| GET | `/tagging/rules` | List all rules |
| GET | `/tagging/rules/<id>` | Get a rule |
| PUT | `/tagging/rules/<id>` | Update a rule |
| DELETE | `/tagging/rules/<id>` | Delete a rule |
| POST | `/tagging/test` | Dry-run test |
| POST | `/tagging/apply` | Bulk apply |

## Testing

20 tests: CRUD (10), pattern matching (7), bulk apply (3).
