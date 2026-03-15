# Multi-Currency & FX Conversion Support

Issue: [#95](https://github.com/rohitdash08/FinMind/issues/95)

## Overview

Full multi-currency support with exchange-rate management, real-time conversion,
and currency-aware analytics. All existing expense and bill records retain their
original currency while analytics can be viewed in any target currency.

## Data Model

### `exchange_rates`
| Column | Type | Description |
|--------|------|-------------|
| base_currency | VARCHAR(10) | Source currency code |
| target_currency | VARCHAR(10) | Target currency code |
| rate | NUMERIC(18,8) | Conversion rate |
| rate_date | DATE | Rate validity date |
| source | VARCHAR(50) | Rate source (manual/bulk/api) |

Unique constraint on `(base_currency, target_currency, rate_date)`.

### `supported_currencies`
Pre-seeded with 15 currencies (USD, EUR, GBP, INR, JPY, CAD, AUD, CHF, CNY, SGD, HKD, KRW, BRL, MXN, ZAR).

## API Endpoints

### Currency Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/currency/list` | List supported currencies |
| POST | `/currency/seed` | Seed default currencies |

### Exchange Rates
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/currency/rates` | Set/update a single rate |
| POST | `/currency/rates/bulk` | Set multiple rates at once |
| GET | `/currency/rates` | List rates (filterable) |
| GET | `/currency/rates/<base>/<target>` | Get specific rate |

### Conversion & Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/currency/convert` | Convert amount between currencies |
| GET | `/currency/summary` | Multi-currency expense summary |

## Key Features

1. **Automatic Inverse Rates** — Setting USD→INR automatically creates INR→USD
2. **Rate History** — All rates are date-stamped, with fallback to most recent
3. **Bulk Import** — Set rates for multiple currencies in one call
4. **Currency-Aware Analytics** — Aggregate expenses across currencies
5. **Bill Analysis** — Active bills aggregated across currencies
6. **Target Override** — Use `?target=USD` to view summary in any currency
7. **Identity Rate** — Same-currency conversion returns 1:1 without DB lookup

## Usage Examples

### Set Exchange Rate
```bash
POST /currency/rates
{
  "base_currency": "USD",
  "target_currency": "INR",
  "rate": 83.5
}
```

### Bulk Set Rates
```bash
POST /currency/rates/bulk
{
  "base_currency": "USD",
  "rates": {"EUR": 0.92, "GBP": 0.79, "INR": 83.5}
}
```

### Convert Amount
```bash
POST /currency/convert
{"amount": 1000, "from": "INR", "to": "USD"}

→ {"original_amount": "1000", "converted_amount": "11.98", ...}
```

### Multi-Currency Summary
```bash
GET /currency/summary?target=USD

→ {
    "target_currency": "USD",
    "expenses": {
      "breakdown": [...],
      "grand_total": "1234.56",
      "currencies_used": 3
    },
    "bills": {...}
  }
```

## Testing

24 tests covering:
- Currency seeding & listing (4 tests)
- Exchange rate CRUD & inverse (7 tests)
- Bulk rate import (1 test)
- Conversion logic (5 tests)
- Multi-currency summary analytics (4 tests)
- Edge cases: identity rates, missing rates, auth

## Backwards Compatibility

- Existing `currency` fields on Expense, Bill, RecurringExpense are unchanged
- Default currency remains `INR` per user preference
- No breaking changes to existing endpoints
