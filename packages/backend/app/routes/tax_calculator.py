"""Tax Calculator API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.tax_calculator import TaxCalculatorService

bp = Blueprint("tax_calculator", __name__)

_services = {}

def _get_service(user_id: str) -> TaxCalculatorService:
    if user_id not in _services:
        _services[user_id] = TaxCalculatorService()
    return _services[user_id]


@bp.post("/calculate")
@jwt_required()
def calculate_tax():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.calculate_federal_tax(
        gross_income=float(data.get("gross_income", 0)),
        filing_status=data.get("filing_status", "single"),
        deductions=data.get("deductions"),
        credits=data.get("credits"),
        withholdings=float(data.get("withholdings", 0)),
    ))


@bp.post("/quarterly")
@jwt_required()
def quarterly_estimate():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.estimate_quarterly_tax(
        annual_income=float(data.get("annual_income", 0)),
        filing_status=data.get("filing_status", "single"),
        deductions=data.get("deductions"),
    ))


@bp.post("/capital-gains")
@jwt_required()
def capital_gains():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.calculate_capital_gains(
        short_term_gains=float(data.get("short_term_gains", 0)),
        long_term_gains=float(data.get("long_term_gains", 0)),
        ordinary_income=float(data.get("ordinary_income", 0)),
        filing_status=data.get("filing_status", "single"),
    ))


@bp.post("/deductions")
@jwt_required()
def suggest_deductions():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify({"deductions": service.suggest_deductions(data.get("expenses", {}))})


@bp.post("/withholding")
@jwt_required()
def paycheck_withholding():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.calculate_paycheck_withholding(
        annual_salary=float(data.get("annual_salary", 0)),
        pay_frequency=data.get("pay_frequency", "biweekly"),
        filing_status=data.get("filing_status", "single"),
    ))
