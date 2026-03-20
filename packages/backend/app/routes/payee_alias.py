from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.payee_alias import get_payee_aliases

bp = Blueprint("payee_alias", __name__)


@bp.route("/payee-aliases", methods=["GET"])
@jwt_required()
def payee_aliases():
    """
    GET /insights/payee-aliases?months=6&min_transactions=2

    Groups transaction descriptions by canonical merchant name,
    showing aliases (raw variants) and spend stats per payee.
    """
    user_id = get_jwt_identity()
    try:
        months = int(request.args.get("months", 6))
    except (ValueError, TypeError):
        months = 6
    try:
        min_transactions = int(request.args.get("min_transactions", 2))
    except (ValueError, TypeError):
        min_transactions = 2

    result = get_payee_aliases(
        user_id=int(user_id), months=months, min_transactions=min_transactions
    )

    return jsonify(
        {
            "total_payees_found": result.total_payees_found,
            "summary": result.summary,
            "aliases": [
                {
                    "canonical_name": a.canonical_name,
                    "raw_variants": a.raw_variants,
                    "total_spend": a.total_spend,
                    "transaction_count": a.transaction_count,
                    "category_hint": a.category_hint,
                    "last_seen": a.last_seen,
                }
                for a in result.aliases
            ],
        }
    )