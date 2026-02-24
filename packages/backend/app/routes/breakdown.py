"""
breakdown.py — Essential vs discretionary spending breakdown endpoints.

GET  /breakdown/classifications                   — list user overrides
POST /breakdown/classifications/<category_id>     — set override
DELETE /breakdown/classifications/<category_id>   — remove override
"""
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import Category, CategoryClassification

bp_breakdown = Blueprint("breakdown", __name__)
logger = logging.getLogger("finmind.breakdown_routes")

_VALID_TYPES = {"ESSENTIAL", "DISCRETIONARY", "UNCATEGORISED"}


@bp_breakdown.get("/classifications")
@jwt_required()
def list_classifications():
    """List all user-defined category classifications."""
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(CategoryClassification, Category.name)
        .join(Category, CategoryClassification.category_id == Category.id)
        .filter(CategoryClassification.user_id == uid)
        .all()
    )
    return jsonify([
        {
            "category_id": c.category_id,
            "category_name": name,
            "classification": c.classification,
        }
        for c, name in rows
    ])


@bp_breakdown.post("/classifications/<int:category_id>")
@jwt_required()
def set_classification(category_id: int):
    """Set or update the essential/discretionary classification for a category."""
    uid = int(get_jwt_identity())
    cat = db.session.get(Category, category_id)
    if not cat or cat.user_id != uid:
        return jsonify(error="category not found"), 404

    data = request.get_json() or {}
    cls = (data.get("classification") or "").upper()
    if cls not in _VALID_TYPES:
        return jsonify(error=f"classification must be one of {sorted(_VALID_TYPES)}"), 400

    existing = (
        db.session.query(CategoryClassification)
        .filter_by(user_id=uid, category_id=category_id)
        .first()
    )
    if existing:
        existing.classification = cls
    else:
        db.session.add(CategoryClassification(
            user_id=uid, category_id=category_id, classification=cls
        ))
    db.session.commit()
    return jsonify({"category_id": category_id, "classification": cls})


@bp_breakdown.delete("/classifications/<int:category_id>")
@jwt_required()
def delete_classification(category_id: int):
    """Remove a user-defined classification override."""
    uid = int(get_jwt_identity())
    obj = (
        db.session.query(CategoryClassification)
        .filter_by(user_id=uid, category_id=category_id)
        .first()
    )
    if not obj:
        return jsonify(error="not found"), 404
    db.session.delete(obj)
    db.session.commit()
    return jsonify(message="deleted")
