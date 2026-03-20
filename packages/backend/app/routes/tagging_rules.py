"""
Routes for rule-based auto-tagging and expense categorization (issue #107).
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import TaggingRule, Expense
from ..services.tagging_rules import apply_rules_to_all, _matches
import logging

bp = Blueprint("tagging_rules", __name__)
logger = logging.getLogger("finmind.tagging_rules")

ALLOWED_FIELDS = {"notes", "amount", "category"}
ALLOWED_OPERATORS = {"contains", "starts_with", "ends_with", "equals", "gt", "lt", "gte", "lte"}


def _rule_to_dict(r):
    return {
        "id": r.id,
        "name": r.name,
        "match_field": r.match_field,
        "match_operator": r.match_operator,
        "match_value": r.match_value,
        "action_set_category_id": r.action_set_category_id,
        "action_set_notes_tag": r.action_set_notes_tag,
        "priority": r.priority,
        "active": r.active,
        "created_at": r.created_at.isoformat(),
    }


def _validate(data: dict):
    if not data.get("name"):
        return "name is required"
    if data.get("match_field") not in ALLOWED_FIELDS:
        return f"match_field must be one of {sorted(ALLOWED_FIELDS)}"
    if data.get("match_operator") not in ALLOWED_OPERATORS:
        return f"match_operator must be one of {sorted(ALLOWED_OPERATORS)}"
    if not data.get("match_value"):
        return "match_value is required"
    if not data.get("action_set_category_id") and not data.get("action_set_notes_tag"):
        return "at least one action (action_set_category_id or action_set_notes_tag) is required"
    field = data["match_field"]
    op = data["match_operator"]
    if field == "notes" and op in {"gt", "lt", "gte", "lte"}:
        return f"operator {op} is not valid for field notes"
    if field == "amount" and op in {"contains", "starts_with", "ends_with"}:
        return f"operator {op} is not valid for field amount"
    return None


@bp.get("")
@jwt_required()
def list_rules():
    uid = int(get_jwt_identity())
    rules = (
        db.session.query(TaggingRule)
        .filter_by(user_id=uid)
        .order_by(TaggingRule.priority.desc(), TaggingRule.created_at.asc())
        .all()
    )
    return jsonify([_rule_to_dict(r) for r in rules])


@bp.post("")
@jwt_required()
def create_rule():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    err = _validate(data)
    if err:
        return jsonify(error=err), 400
    rule = TaggingRule(
        user_id=uid,
        name=data["name"].strip(),
        match_field=data["match_field"],
        match_operator=data["match_operator"],
        match_value=data["match_value"].strip(),
        action_set_category_id=data.get("action_set_category_id"),
        action_set_notes_tag=(data.get("action_set_notes_tag") or "").strip() or None,
        priority=int(data.get("priority") or 0),
        active=bool(data.get("active", True)),
    )
    db.session.add(rule)
    db.session.commit()
    logger.info("Rule created user=%s rule=%s", uid, rule.id)
    return jsonify(_rule_to_dict(rule)), 201


@bp.get("/<int:rule_id>")
@jwt_required()
def get_rule(rule_id: int):
    uid = int(get_jwt_identity())
    rule = db.session.query(TaggingRule).filter_by(id=rule_id, user_id=uid).first()
    if not rule:
        return jsonify(error="rule not found"), 404
    return jsonify(_rule_to_dict(rule))


@bp.put("/<int:rule_id>")
@jwt_required()
def update_rule(rule_id: int):
    uid = int(get_jwt_identity())
    rule = db.session.query(TaggingRule).filter_by(id=rule_id, user_id=uid).first()
    if not rule:
        return jsonify(error="rule not found"), 404
    data = request.get_json(silent=True) or {}
    err = _validate(data)
    if err:
        return jsonify(error=err), 400
    rule.name = data["name"].strip()
    rule.match_field = data["match_field"]
    rule.match_operator = data["match_operator"]
    rule.match_value = data["match_value"].strip()
    rule.action_set_category_id = data.get("action_set_category_id")
    rule.action_set_notes_tag = (data.get("action_set_notes_tag") or "").strip() or None
    rule.priority = int(data.get("priority") or 0)
    rule.active = bool(data.get("active", True))
    db.session.commit()
    return jsonify(_rule_to_dict(rule))


@bp.delete("/<int:rule_id>")
@jwt_required()
def delete_rule(rule_id: int):
    uid = int(get_jwt_identity())
    rule = db.session.query(TaggingRule).filter_by(id=rule_id, user_id=uid).first()
    if not rule:
        return jsonify(error="rule not found"), 404
    db.session.delete(rule)
    db.session.commit()
    return "", 204


@bp.post("/apply")
@jwt_required()
def apply_all():
    uid = int(get_jwt_identity())
    result = apply_rules_to_all(uid)
    return jsonify(result)


@bp.post("/preview")
@jwt_required()
def preview_rule():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    err = _validate(data)
    if err:
        return jsonify(error=err), 400
    rule = TaggingRule(
        user_id=uid,
        name=data["name"],
        match_field=data["match_field"],
        match_operator=data["match_operator"],
        match_value=data["match_value"],
        action_set_category_id=data.get("action_set_category_id"),
        action_set_notes_tag=data.get("action_set_notes_tag"),
        priority=int(data.get("priority") or 0),
        active=True,
    )
    expenses = db.session.query(Expense).filter_by(user_id=uid).all()
    matched = []
    for exp in expenses:
        if _matches(rule, exp):
            matched.append({
                "id": exp.id,
                "notes": exp.notes,
                "amount": float(exp.amount),
                "category_id": exp.category_id,
                "spent_at": exp.spent_at.isoformat(),
            })
    return jsonify({"matched_count": len(matched), "matched_expenses": matched[:20]})
