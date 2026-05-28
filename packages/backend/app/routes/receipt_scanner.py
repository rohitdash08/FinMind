"""Receipt Scanner API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.receipt_scanner import ReceiptScannerService

bp = Blueprint("receipt_scanner", __name__)

_services = {}

def _get_service(user_id: str) -> ReceiptScannerService:
    if user_id not in _services:
        _services[user_id] = ReceiptScannerService()
    return _services[user_id]


@bp.post("/scan")
@jwt_required()
def scan_receipt():
    """Scan receipt text (simulated OCR)."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.scan_text(user_id, data.get("text", "")))


@bp.post("/")
@jwt_required()
def upload_receipt():
    """Manually upload receipt."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.upload_receipt(
        user_id=user_id,
        store=data.get("store", ""),
        total=float(data.get("total", 0)),
        date=data.get("date", ""),
        items=data.get("items"),
        raw_text=data.get("raw_text", ""),
        category=data.get("category", ""),
        tax=float(data.get("tax", 0)),
        tip=float(data.get("tip", 0)),
        payment_method=data.get("payment_method", ""),
    ))


@bp.get("/<receipt_id>")
@jwt_required()
def get_receipt(receipt_id: str):
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.get_receipt(receipt_id))


@bp.get("/")
@jwt_required()
def search_receipts():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify({"receipts": service.search(
        user_id,
        query=request.args.get("query"),
        store=request.args.get("store"),
        category=request.args.get("category"),
        date_from=request.args.get("date_from"),
        date_to=request.args.get("date_to"),
        min_amount=request.args.get("min_amount", type=float),
        max_amount=request.args.get("max_amount", type=float),
    )})


@bp.get("/summary")
@jwt_required()
def get_summary():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.get_summary(user_id))


@bp.get("/export")
@jwt_required()
def export_data():
    user_id = str(get_jwt_identity())
    fmt = request.args.get("format", "json")
    service = _get_service(user_id)
    return jsonify(service.export_data(user_id, fmt))


@bp.delete("/<receipt_id>")
@jwt_required()
def delete_receipt(receipt_id: str):
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.delete(receipt_id))
