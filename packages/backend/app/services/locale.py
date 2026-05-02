from babel import Locale, numbers, dates
from flask import current_app


class LocaleFormatter:
  """Locale-aware formatting for dates, numbers, and currencies."""

  CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "JPY": "¥",
    "CNY": "¥",
    "KRW": "₩",
    "BRL": "R$",
    "AED": "د.إ",
    "SGD": "S$",
    "AUD": "A$",
    "CAD": "C$",
    "CHF": "CHF",
    "HKD": "HK$",
    "NZD": "NZ$",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
    "PLN": "zł",
    "THB": "฿",
    "MXN": "MX$",
    "ZAR": "R",
    "RUB": "₽",
    "TRY": "₺",
    "IDR": "Rp",
    "MYR": "RM",
    "PHP": "₱",
    "VND": "₫",
    "EGP": "E£",
    "NGN": "₦",
    "PKR": "₨",
    "BDT": "৳",
    "LKR": "Rs",
    "QAR": "ر.ق",
    "KWD": "د.ك",
    "SAR": "﷼",
    "BHD": "د.ب",
    "OMR": "ر.ع",
  }

  SUPPORTED_LOCALES = [
    "en-US",
    "en-GB",
    "en-IN",
    "en-AU",
    "en-CA",
    "de-DE",
    "fr-FR",
    "es-ES",
    "it-IT",
    "pt-BR",
    "ja-JP",
    "ko-KR",
    "zh-CN",
    "zh-TW",
    "hi-IN",
    "ar-SA",
    "th-TH",
    "vi-VN",
    "tr-TR",
    "pl-PL",
    "ru-RU",
    "nl-NL",
    "sv-SE",
    "da-DK",
    "fi-FI",
    "nb-NO",
    "id-ID",
    "ms-MY",
    "tl-PH",
  ]

  def __init__(self, locale_str="en-US", currency="INR"):
    self.locale = Locale.parse(locale_str, sep="-")
    self.currency = currency
    self.locale_str = locale_str

  def format_currency(self, amount, currency=None):
    """Format amount as currency string."""
    curr = currency or self.currency
    return numbers.format_currency(amount, curr, locale=self.locale)

  def format_number(self, number):
    """Format number with locale-specific grouping."""
    return numbers.format_decimal(number, locale=self.locale)

  def format_date(self, date_obj, format="medium"):
    """Format date according to locale."""
    return dates.format_date(date_obj, format=format, locale=self.locale)

  def format_datetime(self, datetime_obj, format="medium"):
    """Format datetime according to locale."""
    return dates.format_datetime(
      datetime_obj, format=format, locale=self.locale
    )

  def format_percent(self, number):
    """Format number as percentage."""
    return numbers.format_percent(number, locale=self.locale)

  def to_dict(self):
    """Return locale info as dict."""
    num_symbols = self.locale.number_symbols
    return {
      "locale": self.locale_str,
      "currency": self.currency,
      "currency_symbol": self.CURRENCY_SYMBOLS.get(
        self.currency, self.currency
      ),
      "decimal_symbol": num_symbols.get("decimal", "."),
      "grouping_symbol": num_symbols.get("group", ","),
      "supported_locales": self.SUPPORTED_LOCALES,
    }


def get_formatter(user_locale=None, currency=None):
  """Get a LocaleFormatter for the given locale and currency."""
  loc = user_locale or current_app.config.get("DEFAULT_LOCALE", "en-US")
  curr = currency or current_app.config.get("DEFAULT_CURRENCY", "INR")
  return LocaleFormatter(loc, curr)
