# Universal Bank Statement Normalization Layer

## Overview

Normalizes diverse bank statement formats (CSV, OFX/QFX, plain text) into a unified transaction schema. Features auto-detection of format, column mapping, date parsing, and amount parsing with support for multiple currencies and regional formats.

## API Endpoints

All endpoints require JWT authentication. Base path: `/statements`

### POST /statements/normalize

Main endpoint: parse and normalize a bank statement.

**Request Body:**
```json
{
  "content": "<raw statement content>",
  "filename": "statement.csv",
  "format": "csv",
  "column_mapping": {"Datum": "date", "Betrag": "amount"},
  "date_format": "%d/%m/%Y"
}
```

All fields except `content` are optional.

**Response:**
```json
{
  "detected_format": "csv",
  "transactions": [
    {
      "date": "2025-01-15",
      "amount": 50.0,
      "description": "Grocery Store",
      "transaction_type": "debit",
      "reference": "",
      "balance": 1950.0,
      "category_hint": ""
    }
  ],
  "detected_columns": {"Date": "date", "Amount": "amount"},
  "total_rows": 10,
  "parsed_rows": 9,
  "skipped_rows": 1,
  "warnings": ["Row 5: Unrecognized date 'baddate' — skipped"],
  "errors": [],
  "summary": {
    "total_transactions": 9,
    "total_debits": 6,
    "total_credits": 3,
    "total_debit_amount": 2500.00,
    "total_credit_amount": 5000.00,
    "date_range": {"earliest": "2025-01-01", "latest": "2025-03-15"},
    "unique_descriptions": 7
  }
}
```

### POST /statements/detect-format

Detect statement format without parsing.

**Request:** `{"content": "...", "filename": "stmt.ofx"}`
**Response:** `{"format": "ofx"}`

### POST /statements/detect-columns

Auto-detect column mapping from CSV headers.

**Request:** `{"headers": ["Date", "Description", "Amount", "Balance"]}`
**Response:** `{"column_mapping": {"Date": "date", "Description": "description", "Amount": "amount", "Balance": "balance"}}`

## Supported Formats

### CSV
- Auto-detects column headers via pattern matching
- Supports separate debit/credit columns or combined amount column
- Handles currency symbols ($, €, £, ₹) and commas
- European number format (1.234,56)
- 14+ date formats

### OFX/QFX
- Parses STMTTRN transaction elements
- Supports both OFX 2.x (XML) and OFX 1.x (SGML) formats
- Extracts DTPOSTED, TRNAMT, NAME, MEMO, FITID

### Plain Text
- Pattern-based extraction from PDF-extracted text
- Finds lines with date at start and amount at end
- Detects Dr/Cr suffixes for transaction type

## Column Detection Aliases

| Field | Recognized Headers |
|-------|--------------------|
| date | Date, Transaction Date, Txn Date, Posting Date, Value Date, Booked, When |
| amount | Amount, Transaction Amount, Value, Sum, Total |
| debit | Debit, Withdrawal, Debit Amount, Dr |
| credit | Credit, Deposit, Credit Amount, Cr |
| description | Description, Narrative, Details, Particulars, Memo, Notes, Payee, Merchant |
| reference | Reference, Ref, Txn Ref, Check No, Cheque No, Transaction ID |
| balance | Balance, Running Balance, Closing Balance, Available Balance |

## Architecture

- **Service:** `app/services/bank_statement.py` — Parsers and normalization logic
- **Routes:** `app/routes/bank_statement.py` — 3 endpoints
- **Tests:** `tests/test_bank_statement.py` — 32 tests
