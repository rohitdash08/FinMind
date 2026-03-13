from flask import Blueprint, jsonify, request
from src.features.budget_suggestion import BudgetSuggestion
import pandas as pd

budget_api = Blueprint('budget_api', __name__)

@budget_api.route('/suggestions', methods=['POST'])
def get_budget_suggestions():
    try:
        data = request.get_json()
        spending_data = pd.DataFrame(data['spending_data'])
        months = data.get('months', 6)
        budget_suggestion = BudgetSuggestion(spending_data, months)
        suggestions = budget_suggestion.get_suggestions()
        return jsonify({'suggestions': [{'category': s[0], 'lower_bound': s[1], 'upper_bound': s[2]} for s in suggestions]}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# In your app initialization code
# from src.api.budget_suggestion_api import budget_api
# app.register_blueprint(budget_api, url_prefix='/api')