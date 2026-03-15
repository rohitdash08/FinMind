# Bulk Import Validation & Preview

## Overview

Import expenses from CSV or JSON files with comprehensive validation, field mapping, data corrections, and preview before committing. Supports currency symbol cleanup, multiple date formats, category auto-matching, and field name aliases.

## API Endpoints

All endpoints require JWT authentication.

### POST /import/preview

Validate and preview import data before committing.

**Request Body:**
```json
{
  "content": "amount,date,notes\n50,2025-01-01,Lunch\n",
  "filename": "expenses.csv",
  "format": "csv"
}
```

**Response:**
```json
{
  "format": "csv",
  "total_rows": 2,
  "valid_rows": 2,
  "invalid_rows": 0,
  "field_mapping": {"amount": "amount", "date": "date"},
  "rows": [
    {
      "row_number": 1,
      "original": {"amount": "50", "date": "2025-01-01"},
      "parsed": {"amount": 50.0, "date": "2025-01-01", "category_id": null},
      "corrections": {},
      "warnings": [],
      "errors": [],
      "valid": true
    }
  ],
  "warnings": [],
  "errors": [],
  "summary": {
    "total_amount": 150.0,
    "average_amount": 75.0,
    "categories_to_create": 1,
    "rows_with_corrections": 0,
    "date_range": {"earliest": "2025-01-01", "latest": "2025-03-01"}
  }
}
```

### POST /import/execute

Execute the import after user reviews preview.

**Request Body:**
```json
{
  "content": "amount,date,notes\n50,2025-01-01,Lunch\n",
  "filename": "expenses.csv",
  "format": "csv",
  "skip_invalid": true,
  "create_categories": true
}
```

**Response:**
```json
{
  "imported": 5,
  "skipped": 1,
  "categories_created": ["Electronics"],
  "errors": ["Row 3: Invalid amount"],
  "total_amount": 450.00
}
```

### GET /import/template

Get a sample import template.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| format | string | csv | "csv" or "json" |

## Features

### Format Detection
- Automatic detection from file extension (.csv, .json)
- Content-based detection (starts with `[` or `{` → JSON)
- Manual override via `format` parameter

### Field Name Aliases
The importer recognizes common column name variations:

| Canonical | Aliases |
|-----------|---------|
| amount | amount, total, price, cost, value, sum |
| date | date, spent_at, transaction_date, txn_date, when |
| category | category, category_name, type, group |
| notes | notes, description, memo, details, note, comment |
| currency | currency, cur, ccy |

### Data Corrections
- **Currency symbols**: Removes $, €, £, ₹ and commas from amounts
- **Date formats**: Auto-detects 10+ date formats (YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY, etc.)
- **Missing dates**: Defaults to today with a correction note
- **Category matching**: Fuzzy matches against existing user categories

### Validation Rules
- Amount is required and must be a valid number
- Invalid amounts produce row errors (row is marked invalid)
- Future dates produce warnings (still valid)
- Unknown categories produce warnings (will be auto-created on import)
- Unknown columns are skipped with a warning

## Architecture

- **Service:** `app/services/bulk_import.py` — Parsing, validation, import execution
- **Routes:** `app/routes/bulk_import.py` — REST endpoints under `/import`
- **Tests:** `tests/test_bulk_import.py` — 35 tests covering parsing, validation, execution, and routes
