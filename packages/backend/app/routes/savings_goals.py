import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import SavingsGoal, SavingsMilestone, User

bp = Blueprint('savings_goals', __name__)
logger = logging.getLogger('finmind.savings_goals')


@bp.get('')
@jwt_required()
def list_savings_goals():
    uid = int(get_jwt_identity())
    completed = request.args.get('completed')
    query = db.session.query(SavingsGoal).filter_by(user_id=uid)
    if completed is not None:
        query = query.filter_by(completed=(completed.lower() == 'true'))
    goals = query.order_by(SavingsGoal.deadline.asc().nulls_last()).all()
    result = []
    for goal in goals:
        goal_dict = _goal_to_dict(goal)
        goal_dict['progress'] = _calculate_progress(goal)
        goal_dict['milestones'] = [_milestone_to_dict(m) for m in sorted(goal.milestones, key=lambda m: m.target_amount)]
        result.append(goal_dict)
    return jsonify(result)


@bp.post('')
@jwt_required()
def create_savings_goal():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(error='name required'), 400
    target_amount = _parse_amount(data.get('target_amount'))
    if target_amount is None or target_amount <= 0:
        return jsonify(error='target_amount must be positive'), 400
    current_amount = _parse_amount(data.get('current_amount')) or Decimal('0')
    deadline = None
    if data.get('deadline'):
        try:
            deadline = date.fromisoformat(data.get('deadline'))
        except ValueError:
            return jsonify(error='invalid deadline'), 400
    completed = current_amount >= target_amount
    goal = SavingsGoal(
        user_id=uid, name=name, description=data.get('description'),
        target_amount=target_amount, current_amount=current_amount,
        currency=data.get('currency') or (user.preferred_currency if user else 'INR'),
        deadline=deadline, completed=completed,
        completed_at=datetime.utcnow() if completed else None
    )
    db.session.add(goal)
    db.session.flush()
    milestones_data = data.get('milestones', [])
    for m_data in milestones_data:
        m_amount = _parse_amount(m_data.get('target_amount'))
        if m_amount is None or m_amount <= 0:
            continue
        m_reached = current_amount >= m_amount
        milestone = SavingsMilestone(
            goal_id=goal.id, name=(m_data.get('name') or str(float(m_amount))).strip(),
            target_amount=m_amount, reached=m_reached,
            reached_at=datetime.utcnow() if m_reached else None
        )
        db.session.add(milestone)
    db.session.commit()
    result = _goal_to_dict(goal)
    result['progress'] = _calculate_progress(goal)
    result['milestones'] = [_milestone_to_dict(m) for m in sorted(goal.milestones, key=lambda m: m.target_amount)]
    return jsonify(result), 201


@bp.get('/<int:goal_id>')
@jwt_required()
def get_savings_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error='not found'), 404
    result = _goal_to_dict(goal)
    result['progress'] = _calculate_progress(goal)
    result['milestones'] = [_milestone_to_dict(m) for m in sorted(goal.milestones, key=lambda m: m.target_amount)]
    return jsonify(result)

@bp.patch('/<int:goal_id>')
@jwt_required()
def update_savings_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error='not found'), 404
    data = request.get_json() or {}
    previous_amount = goal.current_amount
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify(error='name cannot be empty'), 400
        goal.name = name
    if 'description' in data:
        goal.description = data.get('description')
    if 'target_amount' in data:
        target_amount = _parse_amount(data.get('target_amount'))
        if target_amount is None or target_amount <= 0:
            return jsonify(error='target_amount must be positive'), 400
        goal.target_amount = target_amount
    if 'current_amount' in data:
        current_amount = _parse_amount(data.get('current_amount'))
        if current_amount is None or current_amount < 0:
            return jsonify(error='current_amount must be non-negative'), 400
        goal.current_amount = current_amount
    if 'currency' in data:
        goal.currency = str(data.get('currency') or 'INR')[:10]
    if 'deadline' in data:
        if data.get('deadline'):
            try:
                goal.deadline = date.fromisoformat(data.get('deadline'))
            except ValueError:
                return jsonify(error='invalid deadline'), 400
        else:
            goal.deadline = None
    _update_completion_status(goal)
    _check_milestones(goal, previous_amount)
    db.session.commit()
    result = _goal_to_dict(goal)
    result['progress'] = _calculate_progress(goal)
    result['milestones'] = [_milestone_to_dict(m) for m in sorted(goal.milestones, key=lambda m: m.target_amount)]
    return jsonify(result)

@bp.delete('/<int:goal_id>')
@jwt_required()
def delete_savings_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error='not found'), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify(message='deleted')


@bp.post('/<int:goal_id>/contribute')
@jwt_required()
def contribute_to_goal(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error='not found'), 404
    if goal.completed:
        return jsonify(error='goal already completed'), 400
    data = request.get_json() or {}
    amount = _parse_amount(data.get('amount'))
    if amount is None or amount <= 0:
        return jsonify(error='amount must be positive'), 400
    previous_amount = goal.current_amount
    goal.current_amount = goal.current_amount + amount
    _update_completion_status(goal)
    newly_completed = _check_milestones(goal, previous_amount)
    db.session.commit()
    result = _goal_to_dict(goal)
    result['progress'] = _calculate_progress(goal)
    result['milestones'] = [_milestone_to_dict(m) for m in sorted(goal.milestones, key=lambda m: m.target_amount)]
    if newly_completed:
        result['milestones_completed'] = [{'name': m.name, 'target_amount': float(m.target_amount)} for m in newly_completed]
    if goal.completed:
        result['goal_completed'] = True
    return jsonify(result)

@bp.post('/<int:goal_id>/milestones')
@jwt_required()
def add_milestone(goal_id):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error='not found'), 404
    data = request.get_json() or {}
    target_amount = _parse_amount(data.get('target_amount'))
    if target_amount is None or target_amount <= 0:
        return jsonify(error='target_amount must be positive'), 400
    if target_amount > goal.target_amount:
        return jsonify(error='milestone cannot exceed goal target'), 400
    name = (data.get('name') or str(float(target_amount))).strip()
    reached = goal.current_amount >= target_amount
    milestone = SavingsMilestone(
        goal_id=goal.id, name=name, target_amount=target_amount,
        reached=reached, reached_at=datetime.utcnow() if reached else None
    )
    db.session.add(milestone)
    db.session.commit()
    return jsonify(_milestone_to_dict(milestone)), 201

@bp.delete('/<int:goal_id>/milestones/<int:milestone_id>')
@jwt_required()
def delete_milestone(goal_id, milestone_id):
    uid = int(get_jwt_identity())
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != uid:
        return jsonify(error='goal not found'), 404
    milestone = db.session.get(SavingsMilestone, milestone_id)
    if not milestone or milestone.goal_id != goal_id:
        return jsonify(error='milestone not found'), 404
    db.session.delete(milestone)
    db.session.commit()
    return jsonify(message='deleted')


@bp.get('/dashboard')
@jwt_required()
def savings_goals_dashboard():
    uid = int(get_jwt_identity())
    goals = db.session.query(SavingsGoal).filter_by(user_id=uid).all()
    total_target = sum(float(g.target_amount) for g in goals)
    total_saved = sum(float(g.current_amount) for g in goals)
    completed_count = sum(1 for g in goals if g.completed)
    active_count = sum(1 for g in goals if not g.completed)
    today = date.today()
    upcoming = db.session.query(SavingsGoal).filter_by(user_id=uid, completed=False).filter(SavingsGoal.deadline >= today).order_by(SavingsGoal.deadline.asc()).limit(5).all()
    overdue = db.session.query(SavingsGoal).filter_by(user_id=uid, completed=False).filter(SavingsGoal.deadline < today).order_by(SavingsGoal.deadline.asc()).all()
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_milestones = db.session.query(SavingsMilestone).join(SavingsGoal).filter(SavingsGoal.user_id == uid).filter(SavingsMilestone.reached == True).filter(SavingsMilestone.reached_at >= week_ago).order_by(SavingsMilestone.reached_at.desc()).limit(10).all()
    return jsonify({
        'summary': {'total_goals': len(goals), 'active_goals': active_count, 'completed_goals': completed_count, 'total_target': round(total_target, 2), 'total_saved': round(total_saved, 2), 'overall_progress': round((total_saved / total_target * 100) if total_target > 0 else 0, 2)},
        'upcoming_deadlines': [{'id': g.id, 'name': g.name, 'deadline': g.deadline.isoformat() if g.deadline else None, 'target_amount': float(g.target_amount), 'current_amount': float(g.current_amount), 'progress': _calculate_progress(g)} for g in upcoming],
        'overdue_goals': [{'id': g.id, 'name': g.name, 'deadline': g.deadline.isoformat() if g.deadline else None, 'target_amount': float(g.target_amount), 'current_amount': float(g.current_amount), 'progress': _calculate_progress(g)} for g in overdue],
        'recent_milestones': [{'id': m.id, 'goal_id': m.goal_id, 'goal_name': m.goal.name, 'name': m.name, 'target_amount': float(m.target_amount), 'reached_at': m.reached_at.isoformat() if m.reached_at else None} for m in recent_milestones]
    })


def _goal_to_dict(goal):
    return {'id': goal.id, 'name': goal.name, 'description': goal.description, 'target_amount': float(goal.target_amount), 'current_amount': float(goal.current_amount), 'currency': goal.currency, 'deadline': goal.deadline.isoformat() if goal.deadline else None, 'completed': goal.completed, 'completed_at': goal.completed_at.isoformat() if goal.completed_at else None, 'created_at': goal.created_at.isoformat() if goal.created_at else None, 'updated_at': goal.updated_at.isoformat() if goal.updated_at else None}

def _milestone_to_dict(milestone):
    return {'id': milestone.id, 'goal_id': milestone.goal_id, 'name': milestone.name, 'target_amount': float(milestone.target_amount), 'reached': milestone.reached, 'reached_at': milestone.reached_at.isoformat() if milestone.reached_at else None}

def _calculate_progress(goal):
    if goal.target_amount <= 0:
        return {'percentage': 0.0, 'remaining': 0.0}
    percentage = min(100.0, (float(goal.current_amount) / float(goal.target_amount)) * 100)
    remaining = max(0.0, float(goal.target_amount) - float(goal.current_amount))
    return {'percentage': round(percentage, 2), 'remaining': round(remaining, 2)}

def _parse_amount(raw):
    try:
        return Decimal(str(raw)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return None

def _update_completion_status(goal):
    if goal.current_amount >= goal.target_amount and not goal.completed:
        goal.completed = True
        goal.completed_at = datetime.utcnow()

def _check_milestones(goal, previous_amount):
    newly_completed = []
    for milestone in goal.milestones:
        if not milestone.reached and goal.current_amount >= milestone.target_amount:
            milestone.reached = True
            milestone.reached_at = datetime.utcnow()
            newly_completed.append(milestone)
    return newly_completed
