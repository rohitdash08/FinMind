from flask import render_template
from .models import FinancialAccount

def multi_account_dashboard(user_id):
    accounts = FinancialAccount.query.filter_by(user_id=user_id).all()
    return render_template('multi_account_dashboard.html', accounts=accounts)