# Locale-Aware Formatting

## Overview

FinMind provides locale-aware formatting for dates, numbers, and currencies using the
[Babel](https://babel.pocoo.org/) library. Users can set their preferred locale and
currency, and API responses will include properly formatted values.

## Supported Locales

| Locale    | Language/Region        |
|-----------|------------------------|
| en-US     | English (United States)|
| en-GB     | English (United Kingdom)|
| en-IN     | English (India)        |
| en-AU     | English (Australia)    |
| en-CA     | English (Canada)       |
| de-DE     | German (Germany)       |
| fr-FR     | French (France)        |
| es-ES     | Spanish (Spain)        |
| it-IT     | Italian (Italy)        |
| pt-BR     | Portuguese (Brazil)    |
| ja-JP     | Japanese (Japan)       |
| ko-KR     | Korean (South Korea)   |
| zh-CN     | Chinese (Simplified)   |
| zh-TW     | Chinese (Traditional)  |
| hi-IN     | Hindi (India)          |
| ar-SA     | Arabic (Saudi Arabia)  |
| th-TH     | Thai (Thailand)        |
| vi-VN     | Vietnamese (Vietnam)   |
| tr-TR     | Turkish (Turkey)       |
| pl-PL     | Polish (Poland)        |
| ru-RU     | Russian (Russia)       |
| nl-NL     | Dutch (Netherlands)    |
| sv-SE     | Swedish (Sweden)       |
| da-DK     | Danish (Denmark)       |
| fi-FI     | Finnish (Finland)      |
| nb-NO     | Norwegian Bokmål       |
| id-ID     | Indonesian (Indonesia) |
| ms-MY     | Malay (Malaysia)       |
| tl-PH     | Filipino (Philippines) |

## Supported Currencies

| Code | Symbol | Name              |
|------|--------|-------------------|
| USD  | $      | US Dollar         |
| EUR  | €      | Euro              |
| GBP  | £      | British Pound     |
| INR  | ₹      | Indian Rupee      |
| JPY  | ¥      | Japanese Yen      |
| CNY  | ¥      | Chinese Yuan      |
| KRW  | ₩      | South Korean Won  |
| BRL  | R$     | Brazilian Real    |
| AED  | د.إ    | UAE Dirham        |
| SGD  | S$     | Singapore Dollar  |
| AUD  | A$     | Australian Dollar |
| CAD  | C$     | Canadian Dollar   |
| CHF  | CHF    | Swiss Franc       |
| HKD  | HK$    | Hong Kong Dollar  |
| NZD  | NZ$    | New Zealand Dollar|
| THB  | ฿      | Thai Baht         |
| MXN  | MX$    | Mexican Peso      |
| ZAR  | R      | South African Rand|
| RUB  | ₽      | Russian Ruble     |
| TRY  | ₺      | Turkish Lira      |
| PKR  | ₨      | Pakistani Rupee   |

## API Endpoints

### Get Locale Info

```
GET /auth/locale
Authorization: Bearer <access_token>
```

Returns the user's locale formatting information:

```json
{
  "locale": "en-US",
  "currency": "USD",
  "currency_symbol": "$",
  "decimal_symbol": ".",
  "grouping_symbol": ",",
  "supported_locales": ["en-US", "en-GB", ...]
}
```

### Get Supported Options

```
GET /auth/locale/options
Authorization: Bearer <access_token>
```

Returns all supported locale, currency, and timezone options:

```json
{
  "locales": ["en-US", "de-DE", ...],
  "currencies": ["AED", "AUD", "BRL", ...],
  "timezones": ["Asia/Kolkata", "UTC", ...]
}
```

### Update User Preferences

```
PATCH /auth/me
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "preferred_currency": "EUR",
  "preferred_locale": "de-DE",
  "preferred_timezone": "Europe/Berlin"
}
```

### Get User Profile (includes locale fields)

```
GET /auth/me
Authorization: Bearer <access_token>
```

Response:

```json
{
  "id": 1,
  "email": "user@example.com",
  "preferred_currency": "EUR",
  "preferred_locale": "de-DE",
  "preferred_timezone": "Europe/Berlin"
}
```

## Using the Locale Service

### In Route Handlers

```python
from ..services.locale import get_formatter

@bp.get("/some-endpoint")
@jwt_required()
def my_endpoint():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)

    formatter = get_formatter(
        user.preferred_locale,
        user.preferred_currency
    )

    return jsonify(
        formatted_amount=formatter.format_currency(1234.56),
        formatted_date=formatter.format_date(date.today()),
        formatted_number=formatter.format_number(98765.43),
    )
```

### Direct Instantiation

```python
from app.services.locale import LocaleFormatter

# German locale with Euro
fmt = LocaleFormatter("de-DE", "EUR")
print(fmt.format_currency(1234.56))    # "1.234,56 €"
print(fmt.format_number(1234567.89))   # "1.234.567,89"
print(fmt.format_date(date.today()))   # "15.01.2024"

# Indian locale with Rupee
fmt = LocaleFormatter("en-IN", "INR")
print(fmt.format_currency(1234567.89))  # "₹12,34,567.89"

# Japanese locale with Yen
fmt = LocaleFormatter("ja-JP", "JPY")
print(fmt.format_currency(123456))      # "￥123,456"
```

### Formatting Examples by Locale

| Locale | Amount       | Number        | Date          |
|--------|-------------|---------------|---------------|
| en-US  | $1,234.56   | 1,234,567.89  | Jan 15, 2024  |
| de-DE  | 1.234,56 €  | 1.234.567,89  | 15.01.2024    |
| fr-FR  | 1 234,56 €  | 1 234 567,89  | 15 janv. 2024 |
| ja-JP  | ￥1,235     | 1,234,568     | 2024/01/15    |
| hi-IN  | ₹12,34,567  | 12,34,567.89  | 15 Jan 2024   |

## Adding New Locales

1. Add the locale string to `LocaleFormatter.SUPPORTED_LOCALES` in `app/services/locale.py`
2. Babel handles the formatting automatically for any locale it supports
3. For new currencies, add the symbol to `LocaleFormatter.CURRENCY_SYMBOLS`
4. Add the currency code to `SUPPORTED_CURRENCIES` in `app/routes/auth.py`

## Database Migration

For existing deployments, the new columns are added automatically via
`_ensure_schema_compatibility()` in `app/__init__.py`:

```sql
ALTER TABLE users
ADD COLUMN IF NOT EXISTS preferred_locale VARCHAR(10) NOT NULL DEFAULT 'en-US';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS preferred_timezone VARCHAR(50) NOT NULL DEFAULT 'UTC';
```

## Configuration

Default locale settings in `app/config.py`:

```python
default_locale: str = "en-US"
default_currency: str = "INR"
default_timezone: str = "UTC"
```

Override via environment variables:

```bash
DEFAULT_LOCALE=en-GB
DEFAULT_CURRENCY=GBP
DEFAULT_TIMEZONE=Europe/London
```
