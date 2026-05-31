from ..extensions import db
from ..models import AutoTagRule, TagCorrection, Expense, Category
import logging

logger = logging.getLogger("finmind.auto_tag")


def evaluate_rules(uid: int, expense: Expense) -> int | None:
    rules = (
        db.session.query(AutoTagRule)
        .filter_by(user_id=uid, enabled=True)
        .order_by(AutoTagRule.priority.desc())
        .all()
    )
    for rule in rules:
        if rule.rule_type == "CATEGORY" and expense.category_id:
            cat = db.session.get(Category, expense.category_id)
            if cat and rule.match_value.lower() in cat.name.lower():
                return rule.target_category_id or cat.id
        elif rule.rule_type == "KEYWORD" and expense.notes:
            keywords = [k.strip().lower() for k in rule.match_value.split(",")]
            if any(kw in expense.notes.lower() for kw in keywords):
                return rule.target_category_id or expense.category_id
    return None


def apply_all_rules(uid: int) -> int:
    expenses = db.session.query(Expense).filter_by(user_id=uid).all()
    applied = 0
    for expense in expenses:
        target_cat = evaluate_rules(uid, expense)
        if target_cat is not None and expense.category_id != target_cat:
            expense.category_id = target_cat
            applied += 1
    db.session.commit()
    logger.info("Applied auto-tag rules user=%s count=%s", uid, applied)
    return applied


def learn_from_correction(
    uid: int, expense_id: int, corrected_category_id: int
) -> dict:
    expense = db.session.get(Expense, expense_id)
    if not expense or expense.user_id != uid:
        return {"error": "expense not found"}
    correction = TagCorrection(
        user_id=uid,
        expense_id=expense_id,
        applied_category_id=expense.category_id,
        corrected_category_id=corrected_category_id,
    )
    db.session.add(correction)
    expense.category_id = corrected_category_id
    db.session.commit()
    logger.info(
        "Learned correction user=%s expense=%s cat=%s",
        uid,
        expense_id,
        corrected_category_id,
    )
    return {"id": correction.id, "applied_category_id": expense.category_id}


def create_rule(uid: int, data: dict) -> AutoTagRule:
    rule = AutoTagRule(
        user_id=uid,
        name=data["name"],
        rule_type=str(data["rule_type"]).upper(),
        match_value=data["match_value"],
        target_category_id=data.get("target_category_id"),
        priority=data.get("priority", 0),
    )
    db.session.add(rule)
    db.session.commit()
    logger.info("Created auto-tag rule id=%s user=%s", rule.id, uid)
    return rule


def list_rules(uid: int) -> list[AutoTagRule]:
    return (
        db.session.query(AutoTagRule)
        .filter_by(user_id=uid)
        .order_by(AutoTagRule.priority.desc())
        .all()
    )


def update_rule(uid: int, rule_id: int, data: dict) -> AutoTagRule | None:
    rule = db.session.get(AutoTagRule, rule_id)
    if not rule or rule.user_id != uid:
        return None
    if "name" in data:
        rule.name = data["name"]
    if "rule_type" in data:
        rule.rule_type = str(data["rule_type"]).upper()
    if "match_value" in data:
        rule.match_value = data["match_value"]
    if "target_category_id" in data:
        rule.target_category_id = data.get("target_category_id")
    if "priority" in data:
        rule.priority = data["priority"]
    if "enabled" in data:
        rule.enabled = data["enabled"]
    db.session.commit()
    return rule


def delete_rule(uid: int, rule_id: int) -> bool:
    rule = db.session.get(AutoTagRule, rule_id)
    if not rule or rule.user_id != uid:
        return False
    db.session.delete(rule)
    db.session.commit()
    return True
