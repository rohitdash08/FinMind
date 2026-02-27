"""Customizable dashboard widgets API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.dashboard_widgets import (
    get_catalog, get_widgets, add_widget, update_widget,
    delete_widget, reorder_widgets,
)

bp = Blueprint("widgets", __name__)


@bp.get("/catalog")
@jwt_required()
def catalog():
    return jsonify(get_catalog())


@bp.get("/")
@jwt_required()
def list_widgets():
    uid = int(get_jwt_identity())
    return jsonify(get_widgets(uid))


@bp.post("/")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("widget_type"):
        return jsonify({"error": "widget_type is required"}), 400
    try:
        result = add_widget(uid, data["widget_type"], data.get("title"),
                            data.get("width", "half"), data.get("config", ""))
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.put("/<int:widget_id>")
@jwt_required()
def update(widget_id):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    result = update_widget(uid, widget_id, **data)
    if not result:
        return jsonify({"error": "Widget not found"}), 404
    return jsonify(result)


@bp.delete("/<int:widget_id>")
@jwt_required()
def remove(widget_id):
    uid = int(get_jwt_identity())
    if delete_widget(uid, widget_id):
        return jsonify({"message": "Widget deleted"})
    return jsonify({"error": "Widget not found"}), 404


@bp.post("/reorder")
@jwt_required()
def reorder():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    ids = data.get("widget_ids", [])
    if not isinstance(ids, list):
        return jsonify({"error": "widget_ids array required"}), 400
    return jsonify(reorder_widgets(uid, ids))
