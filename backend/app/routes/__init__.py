from flask import Blueprint
from . import auth, expenses, bills, reminders, insights
from ..extensions import scheduler

def register_routes(app):
    app.register_blueprint(auth.bp)
    app.register_blueprint(expenses.bp)
    app.register_blueprint(bills.bp)
    app.register_blueprint(reminders.bp)
    app.register_blueprint(insights.bp)

    # Example job registration
    @scheduler.scheduled_job('interval', id='reminder_job', minutes=1)
    def reminder_job():
        app.logger.info("Running reminder job...")
        # Add job logic here