from flask import Flask
from .auth import bp as auth_bp
from .expenses import bp as expenses_bp
from .bills import bp as bills_bp
from .reminders import bp as reminders_bp
from .insights import bp as insights_bp
from .categories import bp as categories_bp
from .docs import bp as docs_bp
from .dashboard import bp as dashboard_bp
from .bank_sync import bp as bank_sync_bp


def register_routes(app: Flask):
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(expenses_bp, url_prefix="/expenses")
    app.register_blueprint(bills_bp, url_prefix="/bills")
    app.register_blueprint(reminders_bp, url_prefix="/reminders")
    app.register_blueprint(insights_bp, url_prefix="/insights")
    app.register_blueprint(categories_bp, url_prefix="/categories")
    app.register_blueprint(docs_bp, url_prefix="/docs")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(bank_sync_bp, url_prefix="/bank-sync")
