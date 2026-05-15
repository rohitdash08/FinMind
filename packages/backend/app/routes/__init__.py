from .auth import bp as auth_bp
from .bills import bp as bills_bp
from .categories import bp as categories_bp
from .dashboard import bp as dashboard_bp
from .docs import bp as docs_bp
from .expenses import bp as expenses_bp
from .insights import bp as insights_bp
from .privacy import bp as privacy_bp
from .reminders import bp as reminders_bp

__all__ = [
    "auth_bp",
    "bills_bp",
    "categories_bp",
    "dashboard_bp",
    "docs_bp",
    "expenses_bp",
    "insights_bp",
    "privacy_bp",
    "reminders_bp",
]