"""
Personal Financial Digital Twin routes (Issue #100).

Endpoints:
  POST /twin/simulate    → run a digital twin simulation
  GET  /twin/event-types → list supported life-change event types
"""

from __future__ import annotations

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.digital_twin import VALID_EVENT_TYPES, run_digital_twin

bp = Blueprint("twin", __name__)
logger = logging.getLogger("finmind.twin")

_EVENT_DOCS = {
    "income_change":    "Persistent change to monthly income. Params: pct_change or amount_change.",
    "expense_change":   "Persistent change to monthly expenses. Params: pct_change or amount_change.",
    "one_time_expense": "Single large expense in a specific month. Params: amount.",
    "one_time_income":  "Windfall / bonus in a specific month. Params: amount.",
    "job_loss":         "Income drops to 0 from this month forward (until job_recovery).",
    "job_recovery":     "Restore income. Params: pct_of_baseline (%) or amount.",
}


@bp.post("/simulate")
@jwt_required()
def simulate():
    """
    Run a personal financial digital twin simulation.

    Request body (JSON):
        horizon_months  (int, 1-60, default 12) — projection horizon
        baseline_months (int, 1-6,  default 3)  — history window for baseline
        anchor          (YYYY-MM-DD, optional)   — projection start date
        events          (list, optional)         — life-change events:
            {
              "type":   "<event_type>",   required
              "month":  "YYYY-MM",        required — when the event takes effect
              "label":  "string",         optional — human-readable label
              + type-specific params (pct_change, amount_change, amount, pct_of_baseline)
            }

    Response:
        baseline       — current avg monthly snapshot
        projections    — month-by-month projected income/expenses/net_flow
        risks          — detected financial risk events (high/medium severity)
        summary        — {total_projected_savings, avg_monthly_net,
                          months_positive, months_negative, final_cumulative_savings}
        horizon_months — int
        events_applied — count of events that fired
        generated_at   — ISO timestamp
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    # horizon_months
    try:
        horizon = int(data.get("horizon_months", 12))
        if not (1 <= horizon <= 60):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="horizon_months must be an integer between 1 and 60"), 400

    # baseline_months
    try:
        baseline = int(data.get("baseline_months", 3))
        if not (1 <= baseline <= 6):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error="baseline_months must be an integer between 1 and 6"), 400

    # anchor
    anchor = None
    if data.get("anchor"):
        try:
            anchor = date.fromisoformat(str(data["anchor"]))
        except ValueError:
            return jsonify(error="anchor must be a valid ISO date (YYYY-MM-DD)"), 400

    # events
    events = data.get("events") or []
    if not isinstance(events, list):
        return jsonify(error="events must be a list"), 400
    if len(events) > 50:
        return jsonify(error="maximum 50 events per simulation"), 400

    # Validate event types
    invalid = [e.get("type") for e in events if e.get("type") not in VALID_EVENT_TYPES]
    if invalid:
        return jsonify(
            error=f"unknown event type(s): {invalid}",
            valid_types=sorted(VALID_EVENT_TYPES),
        ), 400

    # Validate month fields
    for ev in events:
        m = ev.get("month")
        if not m:
            return jsonify(error="each event must have a 'month' field (YYYY-MM)"), 400
        try:
            parts = str(m).split("-")
            if len(parts) != 2:
                raise ValueError
            int(parts[0]), int(parts[1])
        except (ValueError, AttributeError):
            return jsonify(error=f"invalid event month '{m}' — use YYYY-MM format"), 400

    result = run_digital_twin(uid, horizon_months=horizon, events=events,
                              anchor=anchor, baseline_months=baseline)
    return jsonify(result)


@bp.get("/event-types")
@jwt_required()
def event_types():
    """Return the supported life-change event types with descriptions."""
    return jsonify([
        {"type": t, "description": _EVENT_DOCS.get(t, "")}
        for t in sorted(VALID_EVENT_TYPES)
    ])
