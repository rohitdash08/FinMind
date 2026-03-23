from flask import Blueprint, request, jsonify
from ..models import db, SavingsGoal, Milestone
from ..extensions import jwt_required, get_jwt_identity

savings_bp = Blueprint('savings', __name__)

@savings_bp.route('/goals', methods=['POST'])
@jwt_required()
def create_savings_goal():
    data = request.get_json()
    user_id = get_jwt_identity()
    new_goal = SavingsGoal(
        user_id=user_id,
        name=data['name'],
        target_amount=data['target_amount'],
        description=data.get('description')
    )
    db.session.add(new_goal)
    db.session.commit()
    return jsonify({'message': 'Savings goal created successfully'}), 201

@savings_bp.route('/goals/<int:goal_id>/milestones', methods=['POST'])
@jwt_required()
def create_milestone(goal_id):
    data = request.get_json()
    new_milestone = Milestone(
        savings_goal_id=goal_id,
        name=data['name'],
        amount=data['amount'],
        description=data.get('description')
    )
    db.session.add(new_milestone)
    db.session.commit()
    return jsonify({'message': 'Milestone created successfully'}), 201

@savings_bp.route('/goals', methods=['GET'])
@jwt_required()
def get_savings_goals():
    user_id = get_jwt_identity()
    goals = SavingsGoal.query.filter_by(user_id=user_id).all()
    return jsonify([{'id': goal.id, 'name': goal.name, 'target_amount': goal.target_amount, 'current_amount': goal.current_amount, 'description': goal.description} for goal in goals]), 200

@savings_bp.route('/goals/<int:goal_id>/milestones', methods=['GET'])
@jwt_required()
def get_milestones(goal_id):
    milestones = Milestone.query.filter_by(savings_goal_id=goal_id).all()
    return jsonify([{'id': milestone.id, 'name': milestone.name, 'amount': milestone.amount, 'description': milestone.description} for milestone in milestones]), 200