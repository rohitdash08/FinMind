import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from ..extensions import db
from ..models import Category
from ..services.households import household_ids_for_user, is_household_member

bp = Blueprint("categories", __name__)
logger = logging.getLogger("finmind.categories")


@bp.get("")
@jwt_required()
def list_categories():
    uid = int(get_jwt_identity())
    ids = household_ids_for_user(uid)
    query = db.session.query(Category)
    if ids:
        query = query.filter(
            or_(Category.user_id == uid, Category.household_id.in_(ids))
        )
    else:
        query = query.filter(Category.user_id == uid)
    items = query.order_by(Category.name).all()
    logger.info("List categories for user=%s count=%s", uid, len(items))
    return jsonify(
        [{"id": c.id, "name": c.name, "household_id": c.household_id} for c in items]
    )


@bp.post("")
@jwt_required()
def create_category():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        logger.warning("Create category missing name user=%s", uid)
        return jsonify(error="name required"), 400
    household_id = data.get("household_id")
    if household_id is not None:
        try:
            household_id = int(household_id)
        except (TypeError, ValueError):
            return jsonify(error="invalid household_id"), 400
        if not is_household_member(uid, household_id):
            return jsonify(error="forbidden"), 403

    # Optional: enforce unique name per owner scope
    if household_id is None:
        exists = (
            db.session.query(Category)
            .filter_by(user_id=uid, household_id=None, name=name)
            .first()
        )
    else:
        exists = (
            db.session.query(Category)
            .filter_by(household_id=household_id, name=name)
            .first()
        )
    if exists:
        return jsonify(error="category already exists"), 409
    c = Category(user_id=uid, household_id=household_id, name=name)
    db.session.add(c)
    db.session.commit()
    logger.info("Created category id=%s user=%s", c.id, uid)
    return jsonify(id=c.id, name=c.name, household_id=c.household_id), 201


@bp.patch("/<int:category_id>")
@jwt_required()
def update_category(category_id: int):
    uid = int(get_jwt_identity())
    c = db.session.get(Category, category_id)
    if not c:
        return jsonify(error="not found"), 404
    if c.household_id is None and c.user_id != uid:
        return jsonify(error="not found"), 404
    if c.household_id is not None and not is_household_member(uid, c.household_id):
        return jsonify(error="forbidden"), 403
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    c.name = name
    db.session.commit()
    logger.info("Updated category id=%s user=%s", c.id, uid)
    return jsonify(id=c.id, name=c.name, household_id=c.household_id)


@bp.delete("/<int:category_id>")
@jwt_required()
def delete_category(category_id: int):
    uid = int(get_jwt_identity())
    c = db.session.get(Category, category_id)
    if not c:
        return jsonify(error="not found"), 404
    if c.household_id is None and c.user_id != uid:
        return jsonify(error="not found"), 404
    if c.household_id is not None and not is_household_member(uid, c.household_id):
        return jsonify(error="forbidden"), 403
    db.session.delete(c)
    db.session.commit()
    logger.info("Deleted category id=%s user=%s", c.id, uid)
    return jsonify(message="deleted")
