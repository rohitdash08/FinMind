# Advanced Search Across Transactions & Bills

## Overview

Advanced search provides a unified search experience across all financial data —
expenses, bills, and recurring expenses — with powerful filtering, sorting, and
pagination capabilities.

Resolves: [#105](https://github.com/rohitdash08/FinMind/issues/105)

## Features

- **Full-text search** — Search by merchant name, notes, bill name (case-insensitive, partial match)
- **Category filtering** — Filter results by category ID
- **Amount range** — Filter by minimum/maximum amount
- **Date range** — Filter by start/end date
- **Expense type** — Filter by EXPENSE or INCOME
- **Entity type** — Search across expenses, bills, recurring, or any combination
- **Sorting** — Sort by date, amount, name, or type (ascending/descending)
- **Pagination** — Page-based with configurable page size (max 200)
- **Autocomplete suggestions** — Type-ahead search across notes, bill names, and categories
- **Search statistics** — Overview of searchable data with date ranges

## API Endpoints

### `GET /search`

Search across all financial entities.

**Query Parameters:**

| Parameter      | Type    | Default  | Description                                     |
|----------------|---------|----------|-------------------------------------------------|
| `q`            | string  | —        | Search text (matches notes/names, case-insensitive) |
| `category_id`  | integer | —        | Filter by category ID                           |
| `amount_min`   | float   | —        | Minimum amount                                  |
| `amount_max`   | float   | —        | Maximum amount                                  |
| `date_from`    | string  | —        | Start date (YYYY-MM-DD)                         |
| `date_to`      | string  | —        | End date (YYYY-MM-DD)                           |
| `expense_type` | string  | —        | `EXPENSE` or `INCOME`                           |
| `types`        | string  | all      | Comma-separated: `expenses,bills,recurring`     |
| `sort_by`      | string  | `date`   | Sort field: `date`, `amount`, `name`, `type`    |
| `sort_order`   | string  | `desc`   | Sort direction: `asc` or `desc`                 |
| `page`         | integer | `1`      | Page number (1-based)                           |
| `page_size`    | integer | `50`     | Results per page (max 200)                      |

**Response:**

```json
{
  "results": [
    {
      "id": 1,
      "type": "expense",
      "name": "Starbucks Coffee",
      "amount": 5.75,
      "currency": "USD",
      "category": "Food",
      "category_id": 3,
      "date": "2024-06-15",
      "expense_type": "EXPENSE",
      "created_at": "2024-06-15T10:30:00"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 50,
  "total_pages": 1,
  "has_more": false
}
```

### `GET /search/suggestions`

Get autocomplete suggestions based on a prefix.

**Query Parameters:**

| Parameter | Type    | Default | Description                     |
|-----------|---------|--------|---------------------------------|
| `q`       | string  | —      | Search prefix (min 2 chars)     |
| `limit`   | integer | `10`   | Max suggestions (1-50)          |

**Response:**

```json
{
  "suggestions": [
    {"text": "Starbucks Coffee", "type": "expense"},
    {"text": "Streaming", "type": "category"}
  ]
}
```

### `GET /search/stats`

Get search statistics for the authenticated user.

**Response:**

```json
{
  "expense_count": 156,
  "bill_count": 8,
  "category_count": 12,
  "recurring_count": 3,
  "total_searchable": 167,
  "date_range": {
    "earliest": "2024-01-15",
    "latest": "2024-06-30"
  }
}
```

## Technical Details

### Architecture

- **Service layer** (`app/services/search.py`) — Core search logic, independent of HTTP layer
- **Route layer** (`app/routes/search.py`) — Flask blueprint with input validation
- No new database tables — searches existing `expenses`, `bills`, and `recurring_expenses` tables

### Performance

- Uses SQLAlchemy query building with selective filtering (only applies filters when parameters are provided)
- Case-insensitive search via `ILIKE` (PostgreSQL) / `LIKE` (SQLite)
- Pagination prevents large result sets
- Suggestions include deduplication

### Search Behavior

- Text search (`q`) uses partial matching (`%query%`)
- All filters are AND-combined
- Multiple entity types are searched in parallel, then merged and sorted
- Results from different entity types are normalized to a common schema
