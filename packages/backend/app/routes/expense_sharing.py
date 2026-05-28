"""Expense Sharing API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.expense_sharing import ExpenseSharingService

bp = Blueprint("expense_sharing", __name__)

_services = {}

def _get_service(user_id: str) -> ExpenseSharingService:
    if user_id not in _services:
        _services[user_id] = ExpenseSharingService()
    return _services[user_id]


@bp.post("/groups")
@jwt_required()
def create_group():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.create_group(
        name=data.get("name", "New Group"),
        creator_id=user_id,
    ))


@bp.post("/groups/<group_id>/join")
@jwt_required()
def join_group(group_id: str):
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.join_group(group_id, user_id))


@bp.post("/split")
@jwt_required()
def split_expense():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.split_expense(
        payer_id=user_id,
        total_amount=float(data.get("amount", 0)),
        description=data.get("description", ""),
        split_type=data.get("split_type", "equal"),
        participants=data.get("participants", [user_id]),
        custom_splits=data.get("custom_splits"),
        group_id=data.get("group_id"),
        category=data.get("category", ""),
    ))


@bp.post("/settle/<expense_id>")
@jwt_required()
def settle(expense_id: str):
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.settle(
        expense_id=expense_id,
        user_id=user_id,
        amount=float(data.get("amount", 0)),
    ))


@bp.get("/balance")
@jwt_required()
def get_balance():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    group_id = request.args.get("group_id")
    return jsonify(service.get_balance(group_id))


@bp.get("/expenses")
@jwt_required()
def get_expenses():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify({"expenses": service.get_user_expenses(user_id)})
