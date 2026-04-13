"""Rule-based auto-tagging & categorization endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import TaggingRule, Expense
import logging

bp = Blueprint("tagging", __name__)
logger = logging.getLogger("finmind.tagging")

VALID_FIELDS = {"notes", "amount", "expense_type"}
VALID_OPERATORS = {"contains", "equals", "gt", "lt"}


def _rule_to_dict(r):
    return {
        "id": r.id,
        "name": r.name,
        "field": r.field,
        "operator": r.operator,
        "value": r.value,
        "category_id": r.category_id,
        "tag": r.tag,
        "active": r.active,
        "created_at": r.created_at.isoformat(),
    }


def _matches(expense, rule):
    """Check if an expense matches a tagging rule."""
    if rule.field == "notes":
        text = (expense.notes or "").lower()
        if rule.operator == "contains":
            return rule.value.lower() in text
        if rule.operator == "equals":
            return text == rule.value.lower()
    elif rule.field == "amount":
        try:
            val = float(rule.value)
        except ValueError:
            return False
        amt = float(expense.amount)
        if rule.operator == "gt":
            return amt > val
        if rule.operator == "lt":
            return amt < val
        if rule.operator == "equals":
            return amt == val
    elif rule.field == "expense_type":
        if rule.operator == "equals":
            return (expense.expense_type or "").upper() == rule.value.upper()
    return False


@bp.get("")
@jwt_required()
def list_rules():
    uid = int(get_jwt_identity())
    rules = db.session.query(TaggingRule).filter_by(user_id=uid).order_by(TaggingRule.created_at.desc()).all()
    return jsonify([_rule_to_dict(r) for r in rules])


@bp.post("")
@jwt_required()
def create_rule():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    field = (data.get("field") or "").strip().lower()
    if field not in VALID_FIELDS:
        return jsonify(error=f"field must be one of: {', '.join(sorted(VALID_FIELDS))}"), 400
    operator = (data.get("operator") or "").strip().lower()
    if operator not in VALID_OPERATORS:
        return jsonify(error=f"operator must be one of: {', '.join(sorted(VALID_OPERATORS))}"), 400
    value = (data.get("value") or "").strip()
    if not value:
        return jsonify(error="value required"), 400
    rule = TaggingRule(
        user_id=uid, name=name, field=field, operator=operator, value=value,
        category_id=data.get("category_id"), tag=data.get("tag"), active=True,
    )
    db.session.add(rule)
    db.session.commit()
    logger.info("Created tagging rule id=%s user=%s", rule.id, uid)
    return jsonify(_rule_to_dict(rule)), 201


@bp.delete("/<int:rule_id>")
@jwt_required()
def delete_rule(rule_id):
    uid = int(get_jwt_identity())
    rule = db.session.get(TaggingRule, rule_id)
    if not rule or rule.user_id != uid:
        return jsonify(error="not found"), 404
    db.session.delete(rule)
    db.session.commit()
    return jsonify(message="deleted")


@bp.post("/apply")
@jwt_required()
def apply_rules():
    """Apply all active rules to uncategorized expenses."""
    uid = int(get_jwt_identity())
    rules = db.session.query(TaggingRule).filter_by(user_id=uid, active=True).all()
    if not rules:
        return jsonify(matched=0, message="no active rules")
    expenses = db.session.query(Expense).filter_by(user_id=uid).all()
    matched = 0
    for expense in expenses:
        for rule in rules:
            if _matches(expense, rule):
                if rule.category_id and not expense.category_id:
                    expense.category_id = rule.category_id
                    matched += 1
    db.session.commit()
    logger.info("Applied tagging rules user=%s matched=%d", uid, matched)
    return jsonify(matched=matched, total_expenses=len(expenses), rules_applied=len(rules))


@bp.post("/test")
@jwt_required()
def test_rules():
    """Dry-run: show which expenses would be matched without applying."""
    uid = int(get_jwt_identity())
    rules = db.session.query(TaggingRule).filter_by(user_id=uid, active=True).all()
    expenses = db.session.query(Expense).filter_by(user_id=uid).all()
    matches = []
    for expense in expenses:
        for rule in rules:
            if _matches(expense, rule):
                matches.append({
                    "expense_id": expense.id,
                    "expense_notes": expense.notes,
                    "expense_amount": float(expense.amount),
                    "matched_rule": rule.name,
                    "would_assign_category": rule.category_id,
                    "would_assign_tag": rule.tag,
                })
    return jsonify(matches=matches, total_matches=len(matches))
