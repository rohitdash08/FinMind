from flask import Blueprint, jsonify, request
from ..extensions import db
from ..models import User, Account

bp = Blueprint('multi_account', __name__)

@bp.route('/overview', methods=['GET'])
def get_multi_account_overview():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    accounts = Account.query.filter_by(user_id=user_id).all()
    overview = []

    for account in accounts:
        account_overview = {
            'account_id': account.id,
            'balance': account.balance,
            'currency': account.currency,
            'transactions': [t.to_dict() for t in account.transactions]
        }
        overview.append(account_overview)

    return jsonify(overview)