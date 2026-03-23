from flask import Blueprint
from . import auth, expenses, bills, reminders, insights, dashboard

api_bp = Blueprint('api', __name__, url_prefix='/api')

api_bp.register_blueprint(auth.bp)
api_bp.register_blueprint(expenses.bp)
api_bp.register_blueprint(bills.bp)
api_bp.register_blueprint(reminders.bp)
api_bp.register_blueprint(insights.bp)
api_bp.register_blueprint(dashboard.bp)