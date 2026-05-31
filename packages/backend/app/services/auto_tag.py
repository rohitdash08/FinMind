from decimal import Decimal
from ..extensions import db
from ..models import AutoTagRule, TagFeedback, Expense

MATCH_MODES = {
    "keyword": lambda e, v: v.lower() in (e.notes or "").lower(),
    "contains": lambda e, v: v.lower() in (e.notes or "").lower(),
    "equals": lambda e, v: (e.notes or "").lower() == v.lower(),
    "category": lambda e, v: str(e.category_id) == v,
    "amount_gt": lambda e, v: (e.amount or 0) > Decimal(str(v)),
    "amount_lt": lambda e, v: (e.amount or 0) < Decimal(str(v)),
    "amount_range": lambda e, v: _check_amount_range(e.amount, v),
    "expense_type": lambda e, v: (e.expense_type or "").upper() == v.upper(),
}


def _check_amount_range(amount: Decimal, value: str) -> bool:
    parts = value.split(",")
    if len(parts) != 2:
        return False
    try:
        lo, hi = Decimal(parts[0].strip()), Decimal(parts[1].strip())
        return lo <= (amount or 0) <= hi
    except Exception:
        return False


def apply_auto_tags(expense: Expense):
    uid = expense.user_id
    rules = (
        db.session.query(AutoTagRule)
        .filter_by(user_id=uid, active=True)
        .order_by(AutoTagRule.priority.desc())
        .all()
    )
    for rule in rules:
        matcher = MATCH_MODES.get(rule.condition_operator)
        if matcher and matcher(expense, rule.condition_value):
            matches_field = True
            if rule.condition_field == "notes" and rule.condition_operator in ("keyword", "contains", "equals"):
                matches_field = matcher(expense, rule.condition_value)
            elif rule.condition_field == "category_id" and rule.condition_operator == "category":
                matches_field = matcher(expense, rule.condition_value)
            elif rule.condition_field == "amount" and rule.condition_operator in ("amount_gt", "amount_lt", "amount_range"):
                matches_field = matcher(expense, rule.condition_value)
            elif rule.condition_field == "expense_type" and rule.condition_operator == "expense_type":
                matches_field = matcher(expense, rule.condition_value)
            else:
                continue
            if matches_field and rule.target_category_id is not None:
                expense.category_id = rule.target_category_id
                db.session.flush()
                return rule
    return None


def create_rule(user_id: int, data: dict):
    rule = AutoTagRule(
        user_id=user_id,
        name=data["name"],
        condition_field=data.get("condition_field", "notes"),
        condition_operator=data.get("condition_operator", "contains"),
        condition_value=data["condition_value"],
        target_category_id=data.get("target_category_id"),
        priority=data.get("priority", 0),
        active=data.get("active", True),
    )
    db.session.add(rule)
    db.session.commit()
    return rule


def update_rule(rule_id: int, user_id: int, data: dict):
    rule = db.session.query(AutoTagRule).filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        return None
    for field in ("name", "condition_field", "condition_operator", "condition_value", "target_category_id", "priority", "active"):
        if field in data:
            setattr(rule, field, data[field])
    db.session.commit()
    return rule


def delete_rule(rule_id: int, user_id: int) -> bool:
    rule = db.session.query(AutoTagRule).filter_by(id=rule_id, user_id=user_id).first()
    if not rule:
        return False
    db.session.delete(rule)
    db.session.commit()
    return True


def list_rules(user_id: int):
    return (
        db.session.query(AutoTagRule)
        .filter_by(user_id=user_id)
        .order_by(AutoTagRule.priority.desc())
        .all()
    )


def record_feedback(user_id: int, expense_id: int, old_category_id, new_category_id, rule_id=None):
    fb = TagFeedback(
        user_id=user_id,
        expense_id=expense_id,
        old_category_id=old_category_id,
        new_category_id=new_category_id,
        rule_id=rule_id,
    )
    db.session.add(fb)
    db.session.commit()
    return fb


def get_learning_suggestions(user_id: int) -> list[dict]:
    feedbacks = (
        db.session.query(TagFeedback)
        .filter_by(user_id=user_id)
        .order_by(TagFeedback.created_at.desc())
        .limit(50)
        .all()
    )
    corrections = {}
    for fb in feedbacks:
        if fb.old_category_id != fb.new_category_id and fb.rule_id:
            key = f"{fb.old_category_id}->{fb.new_category_id}"
            corrections[key] = corrections.get(key, 0) + 1
    return [
        {"from_category": k.split("->")[0], "to_category": k.split("->")[1], "count": v}
        for k, v in sorted(corrections.items(), key=lambda x: -x[1])
    ]
