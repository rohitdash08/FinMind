import json
import logging
import random
import math
from datetime import datetime, date

from ..extensions import db
from ..models import FinancialTwin, SimulationRun, TwinGoal

logger = logging.getLogger("finmind.digital_twin")


def create_twin(user_id: int, data: dict) -> dict:
    twin = FinancialTwin(
        user_id=user_id,
        name=data.get("name", "My Financial Twin"),
        monthly_income=data.get("monthly_income", 0),
        monthly_expenses=data.get("monthly_expenses", 0),
        savings_rate_pct=data.get("savings_rate_pct", 20),
        current_savings=data.get("current_savings", 0),
        risk_tolerance=data.get("risk_tolerance", "moderate"),
        retirement_age=data.get("retirement_age", 65),
        inflation_rate_pct=data.get("inflation_rate_pct", 6),
        return_rate_pct=data.get("return_rate_pct", 8),
    )
    db.session.add(twin)
    db.session.commit()
    return _twin_to_dict(twin)


def update_twin(user_id: int, twin_id: int, data: dict) -> dict | None:
    twin = FinancialTwin.query.filter_by(id=twin_id, user_id=user_id).first()
    if not twin:
        return None
    for key in ("name", "monthly_income", "monthly_expenses", "savings_rate_pct",
                "current_savings", "risk_tolerance", "retirement_age",
                "inflation_rate_pct", "return_rate_pct"):
        if key in data:
            setattr(twin, key, data[key])
    db.session.commit()
    return _twin_to_dict(twin)


def get_twin(user_id: int, twin_id: int) -> dict | None:
    twin = FinancialTwin.query.filter_by(id=twin_id, user_id=user_id).first()
    return _twin_to_dict(twin) if twin else None


def list_twins(user_id: int) -> list[dict]:
    twins = FinancialTwin.query.filter_by(user_id=user_id, active=True).all()
    return [_twin_to_dict(t) for t in twins]


def delete_twin(user_id: int, twin_id: int) -> bool:
    twin = FinancialTwin.query.filter_by(id=twin_id, user_id=user_id).first()
    if not twin:
        return False
    twin.active = False
    db.session.commit()
    return True


def run_simulation(
    user_id: int,
    twin_id: int,
    scenario_name: str = "baseline",
    projection_years: int = 30,
    num_simulations: int = 1000,
    adjustments: dict | None = None,
) -> dict:
    twin = FinancialTwin.query.filter_by(id=twin_id, user_id=user_id).first()
    if not twin:
        return {"error": "twin not found"}

    adj = adjustments or {}
    monthly_income = float(adj.get("monthly_income", twin.monthly_income))
    monthly_expenses = float(adj.get("monthly_expenses", twin.monthly_expenses))
    current_savings = float(adj.get("current_savings", twin.current_savings))
    savings_rate = float(adj.get("savings_rate_pct", twin.savings_rate_pct)) / 100
    inflation = float(adj.get("inflation_rate_pct", twin.inflation_rate_pct)) / 100
    base_return = float(adj.get("return_rate_pct", twin.return_rate_pct)) / 100
    risk = adj.get("risk_tolerance", twin.risk_tolerance)
    retirement_age = int(adj.get("retirement_age", twin.retirement_age))

    risk_volatility_map = {"conservative": 0.05, "moderate": 0.10, "aggressive": 0.18}
    volatility = risk_volatility_map.get(risk, 0.10)

    paths = []
    final_values = []
    milestones = [5, 10, 15, 20, 25, 30]

    for _ in range(num_simulations):
        savings = current_savings
        annual_income = monthly_income * 12
        annual_expenses = monthly_expenses * 12
        path = [savings]
        for year in range(1, projection_years + 1):
            annual_return = random.gauss(base_return, volatility)
            annual_return = max(annual_return, -0.5)
            monthly_savings = (annual_income - annual_expenses) * savings_rate
            savings = savings * (1 + annual_return) + monthly_savings * 12
            savings = max(savings, 0)
            annual_income *= (1 + inflation)
            annual_expenses *= (1 + inflation)
            path.append(savings)
        paths.append(path)
        final_values.append(savings)

    final_values.sort()
    median_final = final_values[len(final_values) // 2]
    p10 = final_values[int(len(final_values) * 0.1)]
    p90 = final_values[int(len(final_values) * 0.9)]

    percentile_paths = {m: [] for m in milestones}
    for p in paths:
        for m in milestones:
            if m <= projection_years:
                percentile_paths[m].append(p[m])

    milestone_stats = {}
    for m in milestones:
        if m > projection_years:
            break
        vals = sorted(percentile_paths[m])
        milestone_stats[m] = {
            "median": round(vals[len(vals) // 2], 2),
            "p10": round(vals[int(len(vals) * 0.1)], 2),
            "p90": round(vals[int(len(vals) * 0.9)], 2),
        }

    goals = TwinGoal.query.filter_by(twin_id=twin_id, user_id=user_id, achieved=False).all()
    goal_results = []
    for goal in goals:
        target = float(goal.target_amount)
        achieved_count = sum(1 for fv in final_values if fv >= target)
        should_achieve = final_values[len(final_values) // 2] >= target
        median_year = None
        if should_achieve:
            for year in range(1, projection_years + 1):
                year_vals = sorted(p[year] for p in paths)
                if year_vals[len(year_vals) // 2] >= target:
                    median_year = year
                    break
        goal_results.append({
            "goal_id": goal.id,
            "goal_name": goal.name,
            "target_amount": target,
            "success_probability": round(achieved_count / num_simulations * 100, 1),
            "median_achievement_year": median_year,
        })

    success_prob = round(len([f for f in final_values if f >= median_final]) / num_simulations * 100, 1)

    result = {
        "scenario": scenario_name,
        "projection_years": projection_years,
        "num_simulations": num_simulations,
        "twin_config": _twin_to_dict(twin),
        "adjustments": adj,
        "final_stats": {
            "median": round(median_final, 2),
            "p10": round(p10, 2),
            "p90": round(p90, 2),
            "success_probability": success_prob,
        },
        "milestone_stats": milestone_stats,
        "goals": goal_results,
    }

    run = SimulationRun(
        user_id=user_id,
        twin_id=twin_id,
        scenario_name=scenario_name,
        projection_years=projection_years,
        num_simulations=num_simulations,
        result_json=json.dumps(result),
        success_probability=success_prob,
        median_net_worth=round(median_final, 2),
    )
    db.session.add(run)
    db.session.commit()

    logger.info("Simulation run user=%s twin=%s scenario=%s median=%.2f",
                user_id, twin_id, scenario_name, median_final)
    return result


def list_simulations(user_id: int, twin_id: int, limit: int = 20) -> list[dict]:
    runs = (
        SimulationRun.query
        .filter_by(user_id=user_id, twin_id=twin_id)
        .order_by(SimulationRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "scenario_name": r.scenario_name,
            "projection_years": r.projection_years,
            "num_simulations": r.num_simulations,
            "success_probability": float(r.success_probability) if r.success_probability else None,
            "median_net_worth": float(r.median_net_worth) if r.median_net_worth else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ]


def get_simulation(user_id: int, run_id: int) -> dict | None:
    run = SimulationRun.query.filter_by(id=run_id, user_id=user_id).first()
    if not run:
        return None
    return json.loads(run.result_json)


def add_goal(user_id: int, twin_id: int, data: dict) -> dict:
    goal = TwinGoal(
        user_id=user_id,
        twin_id=twin_id,
        name=data.get("name", "Goal"),
        target_amount=data.get("target_amount", 0),
        target_date=datetime.strptime(data["target_date"], "%Y-%m-%d").date(),
        priority=data.get("priority", "medium"),
    )
    db.session.add(goal)
    db.session.commit()
    return _goal_to_dict(goal)


def list_goals(user_id: int, twin_id: int) -> list[dict]:
    goals = TwinGoal.query.filter_by(twin_id=twin_id, user_id=user_id).order_by(TwinGoal.target_date.asc()).all()
    return [_goal_to_dict(g) for g in goals]


def delete_goal(user_id: int, goal_id: int) -> bool:
    goal = TwinGoal.query.filter_by(id=goal_id, user_id=user_id).first()
    if not goal:
        return False
    db.session.delete(goal)
    db.session.commit()
    return True


def _twin_to_dict(twin: FinancialTwin) -> dict:
    return {
        "id": twin.id,
        "name": twin.name,
        "monthly_income": float(twin.monthly_income),
        "monthly_expenses": float(twin.monthly_expenses),
        "savings_rate_pct": float(twin.savings_rate_pct),
        "current_savings": float(twin.current_savings),
        "risk_tolerance": twin.risk_tolerance,
        "retirement_age": twin.retirement_age,
        "inflation_rate_pct": float(twin.inflation_rate_pct),
        "return_rate_pct": float(twin.return_rate_pct),
        "active": twin.active,
        "created_at": twin.created_at.isoformat() if twin.created_at else None,
    }


def _goal_to_dict(goal: TwinGoal) -> dict:
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": float(goal.target_amount),
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "priority": goal.priority,
        "achieved": goal.achieved,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }
