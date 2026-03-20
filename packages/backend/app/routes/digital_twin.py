from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digital_twin import run_digital_twin

bp = Blueprint("digital_twin", __name__)


@bp.route("/digital-twin", methods=["POST"])
@jwt_required()
def financial_digital_twin():
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}
    try:
        projection_months = int(body.get("projection_months", 24))
        starting_balance = float(body.get("starting_balance", 0.0))
        inflation_rate = float(body.get("inflation_rate", 0.03))
        savings_target = body.get("savings_target")
        if savings_target is not None:
            savings_target = float(savings_target)
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid parameter: {e}"}), 400
    life_events = body.get("life_events", [])
    if not isinstance(life_events, list):
        return jsonify({"error": "life_events must be a list"}), 400
    result = run_digital_twin(
        user_id=user_id,
        projection_months=projection_months,
        life_events=life_events,
        savings_target=savings_target,
        inflation_rate=inflation_rate,
        starting_balance=starting_balance,
    )
    return jsonify({
        "baseline": {"monthly_income": result.baseline_monthly_income, "monthly_expenses": result.baseline_monthly_expenses},
        "projection_months": result.projection_months,
        "inflation_rate": result.inflation_rate,
        "life_events_applied": result.life_events_applied,
        "generated_at": result.generated_at,
        "risk_assessment": {"risk_level": result.risk_assessment.risk_level, "risks": result.risk_assessment.risks, "opportunities": result.risk_assessment.opportunities},
        "savings_outlook": {"target": result.savings_outlook.target_amount, "months_to_reach": result.savings_outlook.months_to_reach, "estimated_date": result.savings_outlook.estimated_date} if result.savings_outlook else None,
        "monthly_projections": [{"month": p.month, "income": p.income, "expenses": p.expenses, "net": p.net, "savings_balance": p.savings_balance, "risk_flags": p.risk_flags} for p in result.monthly_projections],
    })
