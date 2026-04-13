from babel import numbers, dates
from datetime import date, datetime
from .models import User
from .extensions import db

class LocaleService:
    @staticmethod
    def format_currency(amount, currency_code, locale='en_US'):
        try:
            return numbers.format_currency(amount, currency_code, locale=locale)
        except:
            return f"{currency_code} {amount:.2f}"

    @staticmethod
    def format_date(d, locale='en_US', format='medium'):
        try:
            return dates.format_date(d, locale=locale, format=format)
        except:
            return str(d)

    @staticmethod
    def get_user_locale(user_id):
        user = db.session.get(User, user_id)
        return user.preferred_locale if user else 'en_US'
