from flask import Blueprint, request, jsonify
from ..models import db, SavingsGoal, Milestone
from ..extensions import jwt_required, get_jwt_identity

bp = Blueprint('savings_goals', __name__, url_prefix='/savings-goals')

@bp.route('/', methods=['POST'])
@jwt_required()
def create_savings_goal():
    data = request.get_json()
    user_id = get_jwt_identity()
    new_goal = SavingsGoal(user_id=user_id, name=data['name'], target_amount=data['target_amount'], description=data.get('description'))
    db.session.add(new_goal)
    db.session.commit()
    return jsonify({'id': new_goal.id, 'name': new_goal.name, 'target_amount': new_goal.target_amount, 'current_amount': new_goal.current_amount, 'description': new_goal.description}), 201

@bp.route('/<int:goal_id>/milestones', methods=['POST'])
@jwt_required()
def create_milestone(goal_id):
    data = request.get_json()
    new_milestone = Milestone(savings_goal_id=goal_id, name=data['name'], amount=data['amount'], description=data.get('description'))
    db.session.add(new_milestone)
    db.session.commit()
    return jsonify({'id': new_milestone.id, 'name': new_milestone.name, 'amount': new_milestone.amount, 'description': new_milestone.description}), 201

@bp.route('/<int:goal_id>', methods=['GET'])
@jwt_required()
def get_savings_goal(goal_id):
    goal = SavingsGoal.query.get_or_404(goal_id)
    milestones = [{'id': m.id, 'name': m.name, 'amount': m.amount, 'description': m.description} for m in goal.milestones]
    return jsonify({'id': goal.id, 'name': goal.name, 'target_amount': goal.target_amount, 'current_amount': goal.current_amount, 'description': goal.description, 'milestones': milestones})

@bp.route('/<int:goal_id>', methods=['PUT'])
@jwt_required()
def update_savings_goal(goal_id):
    data = request.get_json()
    goal = SavingsGoal.query.get_or_404(goal_id)
    goal.name = data.get('name', goal.name)
    goal.target_amount = data.get('target_amount', goal.target_amount)
    goal.description = data.get('description', goal.description)
    db.session.commit()
    return jsonify({'id': goal.id, 'name': goal.name, 'target_amount': goal.target_amount, 'current_amount': goal.current_amount, 'description': goal.description})

@bp.route('/<int:goal_id>', methods=['DELETE'])
@jwt_required()
def delete_savings_goal(goal_id):
    goal = SavingsGoal.query.get_or_404(goal_id)
    db.session.delete(goal)
    db.session.commit()
    return '', 204