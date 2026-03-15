# Locale-Aware Date, Currency & Number Formatting

## Overview

Comprehensive locale-aware formatting system for FinMind that adapts date, currency, and number display to user's regional preferences. Supports 10 locales and 25+ currencies with user-configurable preferences.

## Supported Locales

| Locale | Name | Number Sample | Date Sample |
|--------|------|---------------|-------------|
| en_US | English (US) | 1,234.56 | Mar 15, 2026 |
| en_GB | English (UK) | 1,234.56 | 15 Mar 2026 |
| de_DE | Deutsch | 1.234,56 | 15. Mär 2026 |
| fr_FR | Français | 1 234,56 | 15 mars 2026 |
| es_ES | Español | 1.234,56 | 15 mar 2026 |
| pt_BR | Português | 1.234,56 | 15 mar 2026 |
| ja_JP | 日本語 | 1,234.56 | 2026年03月15日 |
| zh_CN | 中文 | 1,234.56 | 2026年03月15日 |
| hi_IN | हिन्दी | 1,234.56 | 15 Mar 2026 |
| ar_SA | العربية | ١٬٢٣٤٫٥٦ | 15 Mar 2026 |

## API Endpoints

### User Preferences

#### GET /locale/preferences
Get current user's locale preferences.

#### PUT /locale/preferences
Update locale preferences.

```json
{
  "locale": "de_DE",
  "timezone": "Europe/Berlin",
  "date_format": "medium",
  "number_format": "standard",
  "currency_display": "symbol",
  "currency": "EUR"
}
```

### Reference Data

#### GET /locale/locales
List all available locales with formatting samples.

#### GET /locale/currencies
List all 25+ supported currencies with symbols.

#### GET /locale/timezones
List common timezones.

### Formatting Utilities

#### POST /locale/preview
Preview how data will look with given locale settings.

#### POST /locale/format/number
Format a number with locale settings.

#### POST /locale/format/currency
Format a currency amount with locale settings.

#### POST /locale/format/date
Format a date with locale settings.

## Features

### Number Formatting
- Locale-specific decimal separators (`.` vs `,`)
- Locale-specific thousands separators (`,` vs `.` vs ` `)
- Configurable decimal places
- Compact notation (1.2K, 3.4M, 5.6B)
- Percentage formatting

### Currency Formatting
- 25+ currencies with correct symbols
- Currency-specific decimal places (e.g., JPY has 0)
- Three display modes: symbol ($), code (USD), name (US Dollar)
- Locale-specific symbol placement (before vs after amount)
- Compact mode for large values

### Date Formatting
- Four styles: short, medium, long, ISO
- Locale-specific date patterns
- Relative date display (Today, Yesterday, 3 days ago)
- Localized relative words (Heute, 今日, Hoy, etc.)
- DateTime formatting with optional time component

### User Preferences
- Per-user locale settings stored in database
- Configurable timezone, date format, number format
- Currency display preference (symbol/code/name)
- Live formatting preview

## Database Changes

New columns added to `users` table:
- `locale` (VARCHAR(10), default 'en_US')
- `timezone` (VARCHAR(50), default 'UTC')
- `date_format` (VARCHAR(20), default 'YYYY-MM-DD')
- `number_format` (VARCHAR(20), default 'standard')
- `currency_display` (VARCHAR(20), default 'symbol')

## Testing

Run tests:
```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_locale_formatting.py -v
```
