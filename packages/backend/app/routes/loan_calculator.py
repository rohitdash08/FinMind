"""Loan Calculator API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.loan_calculator import LoanCalculatorService

bp = Blueprint("loan_calculator", __name__)

svc = LoanCalculatorService()


@bp.post("/payment")
@jwt_required()
def monthly_payment():
    data = request.get_json() or {}
    return jsonify(svc.calculate_monthly_payment(
        principal=float(data.get("principal", 0)),
        annual_rate=float(data.get("annual_rate", 0)),
        term_months=int(data.get("term_months", 0)),
    ))


@bp.post("/amortization")
@jwt_required()
def amortization():
    data = request.get_json() or {}
    return jsonify(svc.generate_amortization(
        principal=float(data.get("principal", 0)),
        annual_rate=float(data.get("annual_rate", 0)),
        term_months=int(data.get("term_months", 0)),
        extra_payment=float(data.get("extra_payment", 0)),
    ))


@bp.post("/refinance")
@jwt_required()
def refinance():
    data = request.get_json() or {}
    return jsonify(svc.compare_refinance(
        current_balance=float(data.get("current_balance", 0)),
        current_rate=float(data.get("current_rate", 0)),
        current_remaining_months=int(data.get("current_remaining_months", 0)),
        new_rate=float(data.get("new_rate", 0)),
        new_term_months=int(data.get("new_term_months", 0)),
        closing_costs=float(data.get("closing_costs", 0)),
    ))


@bp.post("/compare")
@jwt_required()
def compare():
    data = request.get_json() or {}
    return jsonify(svc.compare_loans(data.get("loans", [])))


@bp.post("/dti")
@jwt_required()
def debt_to_income():
    data = request.get_json() or {}
    return jsonify(svc.debt_to_income(
        monthly_debt=float(data.get("monthly_debt", 0)),
        monthly_income=float(data.get("monthly_income", 0)),
    ))


@bp.post("/payoff")
@jwt_required()
def payoff_date():
    data = request.get_json() or {}
    return jsonify(svc.payoff_date(
        balance=float(data.get("balance", 0)),
        rate=float(data.get("rate", 0)),
        monthly_payment=float(data.get("monthly_payment", 0)),
    ))
