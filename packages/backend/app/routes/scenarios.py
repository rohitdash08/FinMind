"""
Financial Scenario Simulator routes (Issue #94).

Endpoints:
  POST /scenarios/simulate    → run a what-if simulation
  GET  /scenarios/presets     → return common preset adjustment templates
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.scenario_simulator import ADJUSTMENT_TYPES, run_scenario

bp = Blueprint("scenarios", __name__)
logger = logging.getLogger("finmind.scenarios")

# ── Preset templates (no DB needed) ──────────────────────────────────────────

_PRESETS = [
    {
        "id": "reduce_dining_10",
        "label": "Reduce dining out by 10%",
        "description": "Cut restaurant / dining expenses by 10% per month.",
        "adjustments": [{"type": "category_change", "label": "dining", "pct_change": -10}],
    },
    {
        "id": "salary_raise_15",
        "label": "Salary raise +15%",
        "description": "Model a 15% income increase.",
        "adjustments": [{"type": "income_change", "pct_change": 15}],
    },
    {
        "id": "rent_increase_20pct",
        "label": "Rent increase +20%",
        "description": "Model a 20% rent increase as a fixed-cost change.",
        "adjustments": [{"type": "fixed_cost_change", "label": "rent", "pct_change": 20}],
    },
    {
        "id": "lose_job",
        "label": "Job loss (income → 0)",
        "description": "What if your income dropped to zero?",
        "adjustments": [{"type": "income_change", "pct_change": -100}],
    },
    {
        "id": "save_more_50_30_20",
        "label": "Adopt 50/30/20 rule (cut wants by 20%)",
        "description": "Trim discretionary spending by 20% to approach the 50/30/20 budget.",
        "adjustments": [{"type": "category_change", "label": "discretionary", "pct_change": -20}],
    },
]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@bp.post("/simulate")
@jwt_required()
def simulate():
    """
    Run a what-if financial simulation.

    Request body (JSON):
        adjustments (list, required) — list of adjustment objects.
            Each must have:
                type (str): one of 'category_change', 'income_change', 'fixed_cost_change'
            Plus one of:
                pct_change (float)    — percentage change, e.g. -10 = −10%
                amount_change (float) — absolute change in local currency
            For category_change: also category_id (str/int, default 'uncat')
            For fixed_cost_change: also label (str, e.g. 'rent')

        months (int, 1-12, default 3) — look-back window for baseline
        anchor (YYYY-MM-DD, optional) — end date for baseline window

    Response keys:
        baseline, scenario, delta, applied_adjustments, errors,
        analysis_months, generated_at
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    adjustments = data.get("adjustments")
    if not isinstance(adjustments, list) or len(adjustments) == 0:
        return jsonify(error="'adjustments' must be a non-empty list"), 400

    if len(adjustments) > 20:
        return jsonify(error="maximum 20 adjustments per simulation"), 400

    months_raw = data.get("months", 3)
    try:
        months = int(months_raw)
        if not (1 <= months <= 12):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="'months' must be an integer between 1 and 12"), 400

    anchor = None
    if data.get("anchor"):
        try:
            anchor = date.fromisoformat(str(data["anchor"]))
        except ValueError:
            return jsonify(error="'anchor' must be a valid ISO date (YYYY-MM-DD)"), 400

    result = run_scenario(uid, adjustments=adjustments, months=months, anchor=anchor)

    # If all adjustments failed validation, return 422
    if result["errors"] and not result["applied_adjustments"]:
        return jsonify(result), 422

    return jsonify(result), 200


@bp.get("/presets")
@jwt_required()
def list_presets():
    """
    Return a list of common what-if scenario presets.

    Clients can use these templates directly or modify their adjustments
    before posting to /scenarios/simulate.
    """
    return jsonify(_PRESETS)
