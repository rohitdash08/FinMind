"""Personal Financial Digital Twin.

A virtual model of the user's financial life that can simulate
scenarios, project future states, and provide what-if analysis.
"""

import json
from datetime import datetime, date, timedelta
from sqlalchemy import func
from ..extensions import db
from ..models import Expense


class FinancialProfile(db.Model):
    __tablename__ = "financial_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    monthly_income = db.Column(db.Float, default=0)
    monthly_fixed_expenses = db.Column(db.Float, default=0)
    savings_rate = db.Column(db.Float, default=0)  # percentage
    risk_tolerance = db.Column(db.String(20), default="moderate")  # low, moderate, high
    financial_goals = db.Column(db.Text, default="[]")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Simulation(db.Model):
    __tablename__ = "simulations"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    scenario_type = db.Column(db.String(50), nullable=False)
    parameters = db.Column(db.Text, default="{}")
    results = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


SCENARIO_TYPES = [
    "income_change", "expense_reduction", "investment_return",
    "major_purchase", "emergency_fund", "debt_payoff",
    "retirement", "savings_goal",
]


def get_profile(user_id: int) -> dict:
    p = FinancialProfile.query.filter_by(user_id=user_id).first()
    if not p:
        p = FinancialProfile(user_id=user_id)
        db.session.add(p)
        db.session.commit()
    return _serialize_profile(p)


def update_profile(user_id: int, **kwargs) -> dict:
    p = FinancialProfile.query.filter_by(user_id=user_id).first()
    if not p:
        p = FinancialProfile(user_id=user_id)
        db.session.add(p)
    for key in ("monthly_income", "monthly_fixed_expenses", "savings_rate",
                "risk_tolerance", "financial_goals"):
        if key in kwargs and kwargs[key] is not None:
            setattr(p, key, kwargs[key])
    db.session.commit()
    return _serialize_profile(p)


def get_snapshot(user_id: int) -> dict:
    """Current financial state snapshot."""
    today = date.today()
    month_start = date(today.year, today.month, 1)

    monthly_spent = float(db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id, Expense.date >= month_start
    ).scalar() or 0)

    profile = FinancialProfile.query.filter_by(user_id=user_id).first()
    income = profile.monthly_income if profile else 0
    fixed = profile.monthly_fixed_expenses if profile else 0

    # Avg daily spend from last 90 days
    d90 = today - timedelta(days=90)
    total_90 = float(db.session.query(func.sum(Expense.amount)).filter(
        Expense.user_id == user_id, Expense.date >= d90
    ).scalar() or 0)
    avg_daily = total_90 / 90 if total_90 > 0 else 0

    return {
        "date": today.isoformat(),
        "monthly_income": income,
        "monthly_fixed_expenses": fixed,
        "monthly_spent_so_far": round(monthly_spent, 2),
        "avg_daily_spend": round(avg_daily, 2),
        "projected_monthly_spend": round(avg_daily * 30, 2),
        "projected_monthly_savings": round(income - fixed - avg_daily * 30, 2),
        "disposable_remaining": round(income - fixed - monthly_spent, 2),
    }


def simulate(user_id: int, name: str, scenario_type: str, params: dict) -> dict:
    if scenario_type not in SCENARIO_TYPES:
        raise ValueError(f"Unknown scenario: {scenario_type}")

    profile = FinancialProfile.query.filter_by(user_id=user_id).first()
    income = profile.monthly_income if profile else 0
    fixed = profile.monthly_fixed_expenses if profile else 0
    savings_rate = profile.savings_rate if profile else 0

    results = _run_simulation(scenario_type, params, income, fixed, savings_rate)

    sim = Simulation(
        user_id=user_id, name=name, scenario_type=scenario_type,
        parameters=json.dumps(params), results=json.dumps(results),
    )
    db.session.add(sim)
    db.session.commit()

    return {"id": sim.id, "name": name, "scenario_type": scenario_type,
            "parameters": params, "results": results}


def list_simulations(user_id: int) -> list[dict]:
    sims = (Simulation.query.filter_by(user_id=user_id)
            .order_by(Simulation.created_at.desc()).all())
    return [
        {"id": s.id, "name": s.name, "scenario_type": s.scenario_type,
         "created_at": s.created_at.isoformat()}
        for s in sims
    ]


def get_simulation(user_id: int, sim_id: int) -> dict | None:
    s = Simulation.query.filter_by(id=sim_id, user_id=user_id).first()
    if not s:
        return None
    return {"id": s.id, "name": s.name, "scenario_type": s.scenario_type,
            "parameters": json.loads(s.parameters), "results": json.loads(s.results)}


def delete_simulation(user_id: int, sim_id: int) -> bool:
    s = Simulation.query.filter_by(id=sim_id, user_id=user_id).first()
    if not s:
        return False
    db.session.delete(s)
    db.session.commit()
    return True


def _run_simulation(scenario: str, params: dict, income: float,
                    fixed: float, savings_rate: float) -> dict:
    months = int(params.get("months", 12))
    projections = []

    if scenario == "income_change":
        new_income = float(params.get("new_income", income))
        for m in range(1, months + 1):
            savings = new_income - fixed
            projections.append({"month": m, "income": new_income, "savings": round(savings, 2)})
        total_savings = sum(p["savings"] for p in projections)
        return {"projections": projections, "total_savings": round(total_savings, 2),
                "monthly_diff": round(new_income - income, 2)}

    elif scenario == "expense_reduction":
        reduction = float(params.get("reduction_pct", 10)) / 100
        new_fixed = fixed * (1 - reduction)
        for m in range(1, months + 1):
            savings = income - new_fixed
            projections.append({"month": m, "expenses": round(new_fixed, 2), "savings": round(savings, 2)})
        return {"projections": projections, "monthly_saved": round(fixed - new_fixed, 2),
                "total_extra_saved": round((fixed - new_fixed) * months, 2)}

    elif scenario == "major_purchase":
        cost = float(params.get("cost", 0))
        monthly_savings = income - fixed
        months_needed = int(cost / monthly_savings) + 1 if monthly_savings > 0 else 0
        return {"cost": cost, "monthly_savings": round(monthly_savings, 2),
                "months_needed": months_needed, "feasible": monthly_savings > 0}

    elif scenario == "emergency_fund":
        target_months = int(params.get("target_months", 6))
        target = fixed * target_months
        monthly_savings = income - fixed
        months_needed = int(target / monthly_savings) + 1 if monthly_savings > 0 else 0
        return {"target_amount": round(target, 2), "monthly_savings": round(monthly_savings, 2),
                "months_needed": months_needed}

    elif scenario == "savings_goal":
        target = float(params.get("target", 0))
        monthly_savings = income - fixed
        months_needed = int(target / monthly_savings) + 1 if monthly_savings > 0 else 0
        for m in range(1, min(months_needed + 1, months + 1)):
            projections.append({"month": m, "accumulated": round(monthly_savings * m, 2)})
        return {"target": target, "months_needed": months_needed, "projections": projections}

    elif scenario == "investment_return":
        principal = float(params.get("principal", 0))
        annual_return = float(params.get("annual_return_pct", 5)) / 100
        monthly_return = annual_return / 12
        balance = principal
        for m in range(1, months + 1):
            balance *= (1 + monthly_return)
            projections.append({"month": m, "balance": round(balance, 2)})
        return {"final_balance": round(balance, 2), "total_return": round(balance - principal, 2),
                "projections": projections}

    elif scenario == "debt_payoff":
        debt = float(params.get("debt", 0))
        interest_rate = float(params.get("annual_rate_pct", 5)) / 100 / 12
        payment = float(params.get("monthly_payment", 0))
        balance = debt
        m = 0
        while balance > 0 and m < 360:
            m += 1
            interest = balance * interest_rate
            principal_paid = min(payment - interest, balance)
            if principal_paid <= 0:
                return {"error": "Payment too low to cover interest", "min_payment": round(balance * interest_rate, 2)}
            balance -= principal_paid
            projections.append({"month": m, "balance": round(max(balance, 0), 2), "interest": round(interest, 2)})
        total_interest = sum(p["interest"] for p in projections)
        return {"months_to_payoff": m, "total_interest": round(total_interest, 2), "projections": projections}

    elif scenario == "retirement":
        current_savings = float(params.get("current_savings", 0))
        monthly_contrib = float(params.get("monthly_contribution", income - fixed))
        annual_return = float(params.get("annual_return_pct", 6)) / 100 / 12
        years = int(params.get("years", 30))
        balance = current_savings
        for m in range(1, years * 12 + 1):
            balance = balance * (1 + annual_return) + monthly_contrib
            if m % 12 == 0:
                projections.append({"year": m // 12, "balance": round(balance, 2)})
        return {"final_balance": round(balance, 2), "total_contributed": round(current_savings + monthly_contrib * years * 12, 2),
                "projections": projections}

    return {}


def _serialize_profile(p: FinancialProfile) -> dict:
    return {
        "monthly_income": p.monthly_income,
        "monthly_fixed_expenses": p.monthly_fixed_expenses,
        "savings_rate": p.savings_rate,
        "risk_tolerance": p.risk_tolerance,
        "financial_goals": json.loads(p.financial_goals),
    }
