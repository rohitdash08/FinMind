from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.advanced_search import search_transactions

bp = Blueprint("advanced_search", __name__)

@bp.route("/search", methods=["GET"])
@jwt_required()
def advanced_search():
    user_id = get_jwt_identity()
    try:
        amount_min = float(request.args["amount_min"]) if "amount_min" in request.args else None
        amount_max = float(request.args["amount_max"]) if "amount_max" in request.args else None
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 20))
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid parameter: {e}"}), 400
    result = search_transactions(
        user_id=user_id,
        keyword=request.args.get("keyword"),
        category=request.args.get("category"),
        amount_min=amount_min,
        amount_max=amount_max,
        date_from=request.args.get("date_from"),
        date_to=request.args.get("date_to"),
        merchant=request.args.get("merchant"),
        record_type=request.args.get("record_type", "all"),
        page=page,
        page_size=page_size,
    )
    return jsonify({
        "query": result.query,
        "total_expenses": result.total_expenses,
        "total_bills": result.total_bills,
        "total_hits": result.total_hits,
        "page": result.page,
        "page_size": result.page_size,
        "searched_at": result.searched_at,
        "results": [{"type": r.record_type, "id": r.record_id, "description": r.description, "amount": r.amount, "date": r.date_str, "category": r.category, "match_reason": r.match_reason, "extra": r.extra} for r in result.results],
    })
