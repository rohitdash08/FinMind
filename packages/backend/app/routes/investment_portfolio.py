"""Investment Portfolio API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.investment_portfolio import InvestmentPortfolioService

bp = Blueprint("investment_portfolio", __name__)

_services = {}

def _get_service(user_id: str) -> InvestmentPortfolioService:
    if user_id not in _services:
        _services[user_id] = InvestmentPortfolioService()
    return _services[user_id]


@bp.post("/portfolios")
@jwt_required()
def create_portfolio():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.create_portfolio(
        name=data.get("name", "My Portfolio"),
        owner_id=user_id,
        currency=data.get("currency", "USD"),
        initial_cash=float(data.get("initial_cash", 0)),
    ))


@bp.get("/portfolios")
@jwt_required()
def list_portfolios():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify({"portfolios": service.list_portfolios(user_id)})


@bp.post("/portfolios/<pid>/transactions")
@jwt_required()
def record_transaction(pid: str):
    data = request.get_json() or {}
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.record_transaction(
        portfolio_id=pid,
        symbol=data.get("symbol", ""),
        transaction_type=data.get("type", "buy"),
        shares=float(data.get("shares", 0)),
        price=float(data.get("price", 0)),
        fee=float(data.get("fee", 0)),
        date=data.get("date"),
        notes=data.get("notes", ""),
    ))


@bp.post("/portfolios/<pid>/value")
@jwt_required()
def get_value(pid: str):
    data = request.get_json() or {}
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.get_portfolio_value(pid, data.get("prices", {})))


@bp.post("/portfolios/<pid>/allocation")
@jwt_required()
def get_allocation(pid: str):
    data = request.get_json() or {}
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.get_allocation(pid, data.get("prices", {})))


@bp.post("/portfolios/<pid>/performance")
@jwt_required()
def get_performance(pid: str):
    data = request.get_json() or {}
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.calculate_performance(pid, data.get("history", [])))


@bp.post("/portfolios/<pid>/rebalance")
@jwt_required()
def suggest_rebalance(pid: str):
    data = request.get_json() or {}
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.suggest_rebalance(
        pid, data.get("target", {}), data.get("prices", {})))
