import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Category

bp = Blueprint("categories", __name__)
logger = logging.getLogger("finmind.categories")


@bp.get("")
@jwt_required()
def list_categories():
    uid = int(get_jwt_identity())
    items = (
        db.session.query(Category).filter_by(user_id=uid).order_by(Category.name).all()
    )
    logger.info("List categories for user=%s count=%s", uid, len(items))
    return jsonify([{"id": c.id, "name": c.name} for c in items])


@bp.post("")
@jwt_required()
def create_category():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        logger.warning("Create category missing name user=%s", uid)
        return jsonify(error="name required"), 400
    # Optional: enforce unique name per user
    exists = db.session.query(Category).filter_by(user_id=uid, name=name).first()
    if exists:
        return jsonify(error="category already exists"), 409
    c = Category(user_id=uid, name=name)
    db.session.add(c)
    db.session.commit()
    logger.info("Created category id=%s user=%s", c.id, uid)
    return jsonify(id=c.id, name=c.name), 201


@bp.patch("/<int:category_id>")
@jwt_required()
def update_category(category_id: int):
    uid = int(get_jwt_identity())
    c = db.session.get(Category, category_id)
    if not c or c.user_id != uid:
        return jsonify(error="not found"), 404
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    c.name = name
    db.session.commit()
    logger.info("Updated category id=%s user=%s", c.id, uid)
    return jsonify(id=c.id, name=c.name)


@bp.delete("/<int:category_id>")
@jwt_required()
def delete_category(category_id: int):
    uid = int(get_jwt_identity())
    c = db.session.get(Category, category_id)
    if not c or c.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(c)
    db.session.commit()
    logger.info("Deleted category id=%s user=%s", c.id, uid)
    return jsonify(message="deleted")
