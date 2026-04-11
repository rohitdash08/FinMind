"""Routes for AutoTagRule CRUD and rule engine endpoints."""

import json
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import AutoTagRule, Category, Expense, Tag, expense_tags
from ..services.rule_engine import apply_rules, parse_actions, parse_conditions

bp = Blueprint("rules", __name__)
logger = logging.getLogger("finmind.rules")

# ── helpers ────────────────────────────────────────────────────────────────────


def _rule_to_dict(rule: AutoTagRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "priority": rule.priority,
        "conditions": parse_conditions(rule.conditions),
        "actions": parse_actions(rule.actions),
        "active": rule.active,
        "created_at": rule.created_at.isoformat(),
    }


def _validate_conditions(conditions: list) -> str | None:
    """Return an error message if conditions are invalid, else None."""
    valid_fields = {"description", "amount", "expense_type"}
    valid_operators = {"contains", "not_contains", "regex", "equals", "gt", "lt", "between"}
    for i, cond in enumerate(conditions):
        if not isinstance(cond, dict):
            return f"condition[{i}] must be an object"
        if cond.get("field") not in valid_fields:
            return f"condition[{i}].field must be one of {sorted(valid_fields)}"
        if cond.get("operator") not in valid_operators:
            return f"condition[{i}].operator must be one of {sorted(valid_operators)}"
        if "value" not in cond:
            return f"condition[{i}].value is required"
        if cond["operator"] == "between":
            v = cond["value"]
            if not isinstance(v, (list, tuple)) or len(v) != 2:
                return f"condition[{i}].value must be a 2-element array for 'between'"
    return None


def _validate_actions(actions: dict) -> str | None:
    """Return an error message if actions are invalid, else None."""
    if not isinstance(actions, dict):
        return "actions must be an object"
    if not any(k in actions for k in ("set_category_id", "add_tags", "set_expense_type")):
        return "actions must include at least one of: set_category_id, add_tags, set_expense_type"
    tags = actions.get("add_tags")
    if tags is not None and not isinstance(tags, list):
        return "actions.add_tags must be an array"
    exp_type = actions.get("set_expense_type")
    if exp_type is not None and str(exp_type).upper() not in ("EXPENSE", "INCOME"):
        return "actions.set_expense_type must be 'EXPENSE' or 'INCOME'"
    return None


def _get_or_create_tag(uid: int, name: str) -> Tag:
    tag = db.session.query(Tag).filter_by(user_id=uid, name=name).first()
    if not tag:
        tag = Tag(user_id=uid, name=name)
        db.session.add(tag)
        db.session.flush()  # get the id without committing
    return tag


# ── CRUD ───────────────────────────────────────────────────────────────────────


@bp.get("")
@jwt_required()
def list_rules():
    uid = int(get_jwt_identity())
    rules = (
        db.session.query(AutoTagRule)
        .filter_by(user_id=uid)
        .order_by(AutoTagRule.priority.asc(), AutoTagRule.created_at.asc())
        .all()
    )
    return jsonify([_rule_to_dict(r) for r in rules])


@bp.post("")
@jwt_required()
def create_rule():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    conditions = data.get("conditions", [])
    if not isinstance(conditions, list):
        return jsonify(error="conditions must be an array"), 400
    err = _validate_conditions(conditions)
    if err:
        return jsonify(error=err), 400

    actions = data.get("actions", {})
    err = _validate_actions(actions)
    if err:
        return jsonify(error=err), 400

    try:
        priority = int(data.get("priority", 0))
    except (ValueError, TypeError):
        return jsonify(error="priority must be an integer"), 400

    rule = AutoTagRule(
        user_id=uid,
        name=name,
        priority=priority,
        conditions=json.dumps(conditions),
        actions=json.dumps(actions),
        active=bool(data.get("active", True)),
    )
    db.session.add(rule)
    db.session.commit()
    logger.info("Created rule id=%s user=%s name=%s", rule.id, uid, name)
    return jsonify(_rule_to_dict(rule)), 201


@bp.get("/<int:rule_id>")
@jwt_required()
def get_rule(rule_id: int):
    uid = int(get_jwt_identity())
    rule = db.session.get(AutoTagRule, rule_id)
    if not rule or rule.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(_rule_to_dict(rule))


@bp.patch("/<int:rule_id>")
@jwt_required()
def update_rule(rule_id: int):
    uid = int(get_jwt_identity())
    rule = db.session.get(AutoTagRule, rule_id)
    if not rule or rule.user_id != uid:
        return jsonify(error="not found"), 404

    data = request.get_json() or {}

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            return jsonify(error="name required"), 400
        rule.name = name

    if "priority" in data:
        try:
            rule.priority = int(data["priority"])
        except (ValueError, TypeError):
            return jsonify(error="priority must be an integer"), 400

    if "conditions" in data:
        conditions = data["conditions"]
        if not isinstance(conditions, list):
            return jsonify(error="conditions must be an array"), 400
        err = _validate_conditions(conditions)
        if err:
            return jsonify(error=err), 400
        rule.conditions = json.dumps(conditions)

    if "actions" in data:
        actions = data["actions"]
        err = _validate_actions(actions)
        if err:
            return jsonify(error=err), 400
        rule.actions = json.dumps(actions)

    if "active" in data:
        rule.active = bool(data["active"])

    db.session.commit()
    logger.info("Updated rule id=%s user=%s", rule.id, uid)
    return jsonify(_rule_to_dict(rule))


@bp.delete("/<int:rule_id>")
@jwt_required()
def delete_rule(rule_id: int):
    uid = int(get_jwt_identity())
    rule = db.session.get(AutoTagRule, rule_id)
    if not rule or rule.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(rule)
    db.session.commit()
    logger.info("Deleted rule id=%s user=%s", rule.id, uid)
    return jsonify(message="deleted")


# ── dry-run / batch apply ──────────────────────────────────────────────────────


@bp.post("/test")
@jwt_required()
def test_rule():
    """Dry-run: evaluate all active rules against a provided transaction dict.

    Request body:
        {
            "transaction": {
                "description": "Starbucks Coffee",
                "amount": 5.50,
                "expense_type": "EXPENSE"
            }
        }

    Response:
        {
            "matched_rule_ids": [1, 3],
            "changes": {
                "set_category_id": 2,
                "add_tags": ["coffee", "food"],
                "set_expense_type": null
            }
        }
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    transaction = data.get("transaction")
    if not isinstance(transaction, dict):
        return jsonify(error="transaction object required"), 400

    rules = (
        db.session.query(AutoTagRule)
        .filter_by(user_id=uid, active=True)
        .order_by(AutoTagRule.priority.asc(), AutoTagRule.created_at.asc())
        .all()
    )
    rule_dicts = [
        {"id": r.id, "conditions": r.conditions, "actions": r.actions} for r in rules
    ]
    result = apply_rules(transaction, rule_dicts)
    return jsonify(
        matched_rule_ids=result["matched_rule_ids"],
        changes={
            "set_category_id": result["set_category_id"],
            "add_tags": result["add_tags"],
            "set_expense_type": result["set_expense_type"],
        },
    )


@bp.post("/apply-all")
@jwt_required()
def apply_rules_to_all():
    """Batch-apply all active rules to uncategorised existing expenses.

    Only expenses without a category are targeted by default.
    Pass ``{"force": true}`` to re-apply to all expenses.

    Response:
        {"updated": <int>, "skipped": <int>}
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    force = bool(data.get("force", False))

    rules = (
        db.session.query(AutoTagRule)
        .filter_by(user_id=uid, active=True)
        .order_by(AutoTagRule.priority.asc(), AutoTagRule.created_at.asc())
        .all()
    )
    if not rules:
        return jsonify(updated=0, skipped=0)

    rule_dicts = [
        {"id": r.id, "conditions": r.conditions, "actions": r.actions} for r in rules
    ]

    query = db.session.query(Expense).filter_by(user_id=uid)
    if not force:
        query = query.filter(Expense.category_id.is_(None))

    expenses = query.all()
    updated = 0
    skipped = 0

    for expense in expenses:
        exp_dict = {
            "description": expense.notes or "",
            "amount": float(expense.amount),
            "expense_type": expense.expense_type,
            "category_id": expense.category_id,
        }
        result = apply_rules(exp_dict, rule_dicts)

        changed = False
        if result["set_category_id"] is not None:
            # Validate the category belongs to the user
            cat = db.session.get(Category, result["set_category_id"])
            if cat and cat.user_id == uid:
                expense.category_id = result["set_category_id"]
                changed = True

        if result["set_expense_type"]:
            expense.expense_type = result["set_expense_type"]
            changed = True

        for tag_name in result["add_tags"]:
            tag = _get_or_create_tag(uid, tag_name)
            # Avoid duplicates on the association
            current_tag_ids = {t.id for t in expense.tags}
            if tag.id not in current_tag_ids:
                expense.tags.append(tag)
                changed = True

        if changed:
            updated += 1
        else:
            skipped += 1

    db.session.commit()
    logger.info("apply-all rules user=%s updated=%s skipped=%s", uid, updated, skipped)
    return jsonify(updated=updated, skipped=skipped)
