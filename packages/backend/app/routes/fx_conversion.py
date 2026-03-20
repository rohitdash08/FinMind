from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.fx_conversion import get_multi_currency_summary, convert_amount

bp = Blueprint("fx_conversion", __name__)


@bp.route("/currency-summary", methods=["GET"])
@jwt_required()
def currency_summary():
    """
    GET /insights/currency-summary?currency=EUR&months=3

    Returns all spending/income converted to a target currency with
    per-source-currency analytics. Uses ECB historical rates via Frankfurter.app.
    """
    user_id = get_jwt_identity()
    target_currency = request.args.get("currency", "USD").upper()
    try:
        months = int(request.args.get("months", 3))
    except (ValueError, TypeError):
        months = 3

    result = get_multi_currency_summary(
        user_id=int(user_id),
        target_currency=target_currency,
        months=months,
    )

    return jsonify(
        {
            "base_currency": result.base_currency,
            "target_currency": result.target_currency,
            "total_expenses_converted": result.total_expenses_converted,
            "total_income_converted": result.total_income_converted,
            "net_converted": result.net_converted,
            "recent_rate": result.recent_rate,
            "rate_date": result.rate_date,
            "analytics_by_currency": [
                {
                    "currency": a.currency,
                    "total_expenses": a.total_expenses,
                    "total_converted": a.total_converted,
                    "transaction_count": a.transaction_count,
                    "avg_rate_used": a.avg_rate_used,
                }
                for a in result.analytics_by_currency
            ],
        }
    )


@bp.route("/convert", methods=["GET"])
@jwt_required()
def convert():
    """
    GET /insights/convert?amount=100&from=USD&to=EUR

    Simple one-off currency conversion using current ECB rate.
    """
    try:
        amount = float(request.args.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0.0
    from_currency = request.args.get("from", "USD")
    to_currency = request.args.get("to", "EUR")

    result = convert_amount(amount, from_currency, to_currency)
    return jsonify(result)