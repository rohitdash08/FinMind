from flask import Flask
from .auth import bp as auth_bp
from .expenses import bp as expenses_bp
from .bills import bp as bills_bp
from .reminders import bp as reminders_bp
from .insights import bp as insights_bp
from .categories import bp as categories_bp
from .docs import bp as docs_bp
from .dashboard import bp as dashboard_bp
from .reminder_optimization import bp as reminder_optimization_bp
from .auto_tag import bp as auto_tag_bp
from .anomaly_alerts import bp as anomaly_alerts_bp
from .subscriptions import bp as subscriptions_bp
from .statement_normalizer import bp as statement_normalizer_bp


def register_routes(app: Flask):
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(expenses_bp, url_prefix="/expenses")
    app.register_blueprint(bills_bp, url_prefix="/bills")
    app.register_blueprint(reminders_bp, url_prefix="/reminders")
    app.register_blueprint(insights_bp, url_prefix="/insights")
    app.register_blueprint(categories_bp, url_prefix="/categories")
    app.register_blueprint(docs_bp, url_prefix="/docs")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(reminder_optimization_bp, url_prefix="/reminders/optimization")
    app.register_blueprint(auto_tag_bp, url_prefix="/auto-tag")
    app.register_blueprint(anomaly_alerts_bp, url_prefix="/anomaly-alerts")
    app.register_blueprint(subscriptions_bp, url_prefix="/subscriptions")
    app.register_blueprint(statement_normalizer_bp, url_prefix="/statement-normalizer")
