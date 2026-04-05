from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.search import search

bp = Blueprint("search", __name__)

@bp.get("")
@jwt_required()
def search_route():
    uid = int(get_jwt_identity())
    return jsonify(search(
        uid,
        query=request.args.get("q"),
        amount_min=float(request.args["amount_min"]) if "amount_min" in request.args else None,
        amount_max=float(request.args["amount_max"]) if "amount_max" in request.args else None,
        date_from=request.args.get("date_from"),
        date_to=request.args.get("date_to"),
        expense_type=request.args.get("type"),
        category_id=int(request.args["category_id"]) if "category_id" in request.args else None,
        include_bills=request.args.get("include_bills","0") == "1",
        limit=min(int(request.args.get("limit", 50)), 200),
    ))
