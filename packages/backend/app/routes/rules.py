import logging
import re
from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import CategorizationRule, RuleField, RuleOperator, ConditionType, RuleCondition, Category

bp = Blueprint('rules', __name__)
logger = logging.getLogger('finmind.rules')

@bp.get('')
@jwt_required()
def list_rules():
    uid = int(get_jwt_identity())
    rules = db.session.query(CategorizationRule).filter_by(user_id=uid).order_by(CategorizationRule.priority.desc()).all()
    return jsonify([r.to_dict() for r in rules])

@bp.get('/<int:rule_id>')
@jwt_required()
def get_rule(rule_id):
    uid = int(get_jwt_identity())
    rule = db.session.get(CategorizationRule, rule_id)
    if not rule or rule.user_id != uid:
        return jsonify(error='not found'), 404
    return jsonify(rule.to_dict())

@bp.post('')
@jwt_required()
def create_rule():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name: return jsonify(error='name required'), 400
    field = _parse_field(data.get('field'))
    if not field: return jsonify(error='valid field required'), 400
    operator = _parse_operator(data.get('operator'))
    if not operator: return jsonify(error='valid operator required'), 400
    value = (data.get('value') or '').strip()
    if not value: return jsonify(error='value required'), 400
    if operator == RuleOperator.REGEX:
        try: re.compile(value)
        except re.error as e: return jsonify(error='invalid regex: ' + str(e)), 400
    category_id = data.get('category_id')
    if category_id:
        cat = db.session.get(Category, category_id)
        if not cat or cat.user_id != uid: return jsonify(error='category not found'), 404
    try: priority = int(data.get('priority', 0))
    except: return jsonify(error='invalid priority'), 400
    condition_type = _parse_condition_type(data.get('condition_type'))
    rule = CategorizationRule(user_id=uid, name=name, field=field, operator=operator, value=value, category_id=category_id, tag=data.get('tag'), priority=priority, condition_type=condition_type, active=bool(data.get('active', True)))
    db.session.add(rule)
    db.session.commit()
    logger.info('Created rule id=%s user=%s', rule.id, uid)
    conditions = data.get('conditions', [])
    if conditions:
        for cd in conditions:
            cf, co, cv = _parse_field(cd.get('field')), _parse_operator(cd.get('operator')), (cd.get('value') or '').strip()
            if cf and co and cv:
                if co == RuleOperator.REGEX:
                    try:
                        re.compile(cv)
                    except:
                        continue
                db.session.add(RuleCondition(rule_id=rule.id, field=cf, operator=co, value=cv))
        db.session.commit()
    return jsonify(rule.to_dict()), 201


@bp.patch('/<int:rule_id>')
@jwt_required()
def update_rule(rule_id):
    uid = int(get_jwt_identity())
    rule = db.session.get(CategorizationRule, rule_id)
    if not rule or rule.user_id != uid: return jsonify(error='not found'), 404
    data = request.get_json() or {}
    if 'name' in data: rule.name = (data.get('name') or '').strip() or rule.name
    if 'field' in data: rule.field = _parse_field(data.get('field')) or rule.field
    if 'operator' in data: rule.operator = _parse_operator(data.get('operator')) or rule.operator
    if 'value' in data: rule.value = (data.get('value') or '').strip() or rule.value
    if 'category_id' in data: rule.category_id = data.get('category_id')
    if 'tag' in data: rule.tag = data.get('tag')
    if 'priority' in data: try: rule.priority = int(data.get('priority', 0)); except: pass
    if 'active' in data: rule.active = bool(data.get('active'))
    db.session.commit()
    return jsonify(rule.to_dict())

@bp.delete('/<int:rule_id>')
@jwt_required()
def delete_rule(rule_id):
    uid = int(get_jwt_identity())
    rule = db.session.get(CategorizationRule, rule_id)
    if not rule or rule.user_id != uid: return jsonify(error='not found'), 404
    db.session.delete(rule)
    db.session.commit()
    return jsonify(message='deleted')

@bp.post('/<int:rule_id>/conditions')
@jwt_required()
def add_condition(rule_id):
    uid = int(get_jwt_identity())
    rule = db.session.get(CategorizationRule, rule_id)
    if not rule or rule.user_id != uid: return jsonify(error='not found'), 404
    data = request.get_json() or {}
    field = _parse_field(data.get('field'))
    operator = _parse_operator(data.get('operator'))
    value = (data.get('value') or '').strip()
    if not field or not operator or not value: return jsonify(error='field, operator, value required'), 400
    cond = RuleCondition(rule_id=rule_id, field=field, operator=operator, value=value)
    db.session.add(cond)
    db.session.commit()
    return jsonify(cond.to_dict()), 201

@bp.post('/apply/<int:expense_id>')
@jwt_required()
def apply_rules_to_expense(expense_id):
    from ..models import Expense
    uid = int(get_jwt_identity())
    exp = db.session.get(Expense, expense_id)
    if not exp or exp.user_id != uid: return jsonify(error='expense not found'), 404
    result = apply_rules(exp, uid)
    return jsonify(result)


def _parse_field(raw): return RuleField(str(raw).lower().strip()) if raw else None
def _parse_operator(raw): return RuleOperator(str(raw).lower().strip()) if raw else None
def _parse_condition_type(raw): return ConditionType(str(raw).upper().strip()) if raw else ConditionType.AND

def apply_rules(expense, user_id):
    rules = db.session.query(CategorizationRule).filter_by(user_id=user_id, active=True).order_by(CategorizationRule.priority.desc()).all()
    applied = []
    cat_id = None
    tag = None
    for rule in rules:
        if _evaluate_rule(expense, rule):
            applied.append(rule.to_dict())
            if rule.category_id and not cat_id: cat_id = rule.category_id; expense.category_id = cat_id
            if rule.tag and not tag: tag = rule.tag
            if not db.session.query(RuleCondition).filter_by(rule_id=rule.id).first(): break
    if applied: db.session.commit()
    return {'expense_id': expense.id, 'category_id': cat_id, 'tag': tag, 'applied_rules': applied}

def _evaluate_rule(expense, rule):
    conds = db.session.query(RuleCondition).filter_by(rule_id=rule.id).all()
    if not conds: return _evaluate_condition(expense, rule.field, rule.operator, rule.value)
    results = [_evaluate_condition(expense, rule.field, rule.operator, rule.value)]
    for c in conds: results.append(_evaluate_condition(expense, c.field, c.operator, c.value))
    return all(results) if rule.condition_type == ConditionType.AND else any(results)

def _evaluate_condition(expense, field, operator, value):
    fv = str(expense.amount) if field == RuleField.AMOUNT else expense.notes or ''
    if operator == RuleOperator.CONTAINS: return value.lower() in fv.lower()
    elif operator == RuleOperator.EQUALS: return value.lower() == fv.lower()
    elif operator == RuleOperator.STARTSWITH: return fv.lower().startswith(value.lower())
    elif operator == RuleOperator.ENDSWITH: return fv.lower().endswith(value.lower())
    elif operator == RuleOperator.REGEX: try: return bool(re.search(value, fv, re.I)); except: return False
    elif operator in (RuleOperator.GT, RuleOperator.LT, RuleOperator.GTE, RuleOperator.LTE):
        try:
            fn, vn = Decimal(fv), Decimal(value)
            if operator == RuleOperator.GT: return fn > vn
            elif operator == RuleOperator.LT: return fn < vn
            elif operator == RuleOperator.GTE: return fn >= vn
            elif operator == RuleOperator.LTE: return fn <= vn
        except: return False
    return False
