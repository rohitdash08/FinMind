from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_webhook import Webhook

db = SQLAlchemy()
def create_app():
    app.config.from_object('backend.app.config.Config')
    db.init_app(app)

    webhook = Webhook(app)
    webhook.add_event_handler('expense_created', handle_expense_created)
    webhook.add_event_handler('bill_created', handle_bill_created)

    with app.app_context():
        from backend.app.routes import auth, expenses, bills, reminders, insights
        app.register_blueprint(auth.bp)
        app.register_blueprint(insights.bp)

    return app

def handle_expense_created(expense):
    # Logic to handle expense created event
    pass

def handle_bill_created(bill):
    # Logic to handle bill created event
    pass