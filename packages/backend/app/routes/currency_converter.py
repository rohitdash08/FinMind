"""Currency Converter API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.currency_converter import CurrencyConverter

bp = Blueprint("currency_converter", __name__)

_service = CurrencyConverter()


@bp.post("/convert")
@jwt_required()
def convert():
    data = request.get_json() or {}
    return jsonify(_service.convert(
        amount=float(data.get("amount", 0)),
        from_currency=data.get("from", "USD"),
        to_currency=data.get("to", "EUR"),
    ))


@bp.post("/convert/transaction")
@jwt_required()
def convert_transaction():
    data = request.get_json() or {}
    return jsonify(_service.convert_transaction(
        transaction=data.get("transaction", {}),
        target_currency=data.get("target_currency", "USD"),
    ))


@bp.post("/convert/batch")
@jwt_required()
def batch_convert():
    data = request.get_json() or {}
    return jsonify(_service.batch_convert(
        transactions=data.get("transactions", []),
        target_currency=data.get("target_currency", "USD"),
    ))


@bp.get("/rate/<from_curr>/<to_curr>")
@jwt_required()
def get_rate(from_curr: str, to_curr: str):
    return jsonify(_service.get_rate(from_curr, to_curr))


@bp.get("/currencies")
@jwt_required()
def list_currencies():
    return jsonify({"currencies": _service.list_currencies()})


@bp.post("/favorites")
@jwt_required()
def add_favorite():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    return jsonify(_service.add_favorite(
        user_id=user_id,
        from_curr=data.get("from", "USD"),
        to_curr=data.get("to", "EUR"),
    ))


@bp.get("/favorites")
@jwt_required()
def get_favorites():
    user_id = str(get_jwt_identity())
    return jsonify({"favorites": _service.get_favorites(user_id)})
