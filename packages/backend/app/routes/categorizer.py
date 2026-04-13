"""Intelligent categorization endpoints."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Expense
from ..services.categorizer import suggest_category, bulk_categorize
import logging
bp = Blueprint("categorizer", __name__)

@bp.post("/suggest")
@jwt_required()
def suggest():
    data = request.get_json() or {}
    desc = data.get("description", "")
    if not desc:
        return jsonify(error="description required"), 400
    return jsonify(suggest_category(desc))

@bp.post("/bulk")
@jwt_required()
def bulk():
    uid = int(get_jwt_identity())
    expenses = db.session.query(Expense).filter_by(user_id=uid, category_id=None).limit(100).all()
    items = [{"id": e.id, "notes": e.notes, "amount": float(e.amount)} for e in expenses]
    results = bulk_categorize(items)
    return jsonify(results=results, total=len(results), categorized=sum(1 for r in results if r["suggested_category"]))

@bp.get("/keywords")
@jwt_required()
def keywords():
    from ..services.categorizer import KEYWORD_MAP
    categories = {}
    for kw, cat in KEYWORD_MAP.items():
        categories.setdefault(cat, []).append(kw)
    return jsonify(categories=categories)
