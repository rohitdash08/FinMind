from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import db, Household, HouseholdMember, User, MemberRole
from datetime import datetime

households_bp = Blueprint('households', __name__, url_prefix='/api/households')

@households_bp.route('', methods=['POST'])
@jwt_required()
def create_household():
    """Create a new household and add the creator as admin."""
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'Household name is required'}), 400

    current_user_id = get_jwt_identity()
    
    # Check if user is already in a household
    existing = HouseholdMember.query.filter_by(user_id=current_user_id).first()
    if existing:
        return jsonify({'error': 'User is already in a household'}), 400

    try:
        new_household = Household(
            name=data['name'],
            created_by=current_user_id
        )
        db.session.add(new_household)
        db.session.flush()  # Get ID before commit

        # Add creator as admin
        member = HouseholdMember(
            household_id=new_household.id,
            user_id=current_user_id,
            role=MemberRole.ADMIN.value
        )
        db.session.add(member)
        db.session.commit()

        return jsonify({
            'id': new_household.id,
            'name': new_household.name,
            'message': 'Household created successfully'
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@households_bp.route('/<int:household_id>', methods=['GET'])
@jwt_required()
def get_household(household_id):
    """Get household details and members."""
    current_user_id = get_jwt_identity()
    household = Household.query.get(household_id)
    
    if not household:
        return jsonify({'error': 'Household not found'}), 404

    # Check membership
    is_member = HouseholdMember.query.filter_by(
        household_id=household_id, 
        user_id=current_user_id
    ).first()
    
    if not is_member:
        return jsonify({'error': 'Access denied'}), 403

    members = HouseholdMember.query.filter_by(household_id=household_id).all()
    member_list = []
    for m in members:
        user = User.query.get(m.user_id)
        member_list.append({
            'id': user.id,
            'email': user.email,
            'role': m.role,
            'joined_at': m.joined_at.isoformat()
        })

    return jsonify({
        'id': household.id,
        'name': household.name,
        'created_by': household.created_by,
        'created_at': household.created_at.isoformat(),
        'members': member_list
    })

@households_bp.route('/<int:household_id>/members', methods=['POST'])
@jwt_required()
def invite_member(household_id):
    """Invite a user to the household (by email)."""
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data or 'email' not in data:
        return jsonify({'error': 'Email is required'}), 400

    # Verify current user is admin of this household
    membership = HouseholdMember.query.filter_by(
        household_id=household_id, 
        user_id=current_user_id, 
        role=MemberRole.ADMIN.value
    ).first()
    
    if not membership:
        return jsonify({'error': 'Only admins can invite members'}), 403

    # Find user by email
    new_user = User.query.filter_by(email=data['email']).first()
    if not new_user:
        return jsonify({'error': 'User not found'}), 404

    # Check if already a member
    existing = HouseholdMember.query.filter_by(
        household_id=household_id, 
        user_id=new_user.id
    ).first()
    
    if existing:
        return jsonify({'error': 'User is already a member'}), 400

    try:
        new_member = HouseholdMember(
            household_id=household_id,
            user_id=new_user.id,
            role=MemberRole.MEMBER.value
        )
        db.session.add(new_member)
        db.session.commit()
        return jsonify({'message': f'{new_user.email} added to household'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@households_bp.route('/my', methods=['GET'])
@jwt_required()
def get_my_household():
    """Get the household the current user belongs to."""
    current_user_id = get_jwt_identity()
    membership = HouseholdMember.query.filter_by(user_id=current_user_id).first()
    
    if not membership:
        return jsonify({'message': 'User is not in any household'}), 404
        
    household = Household.query.get(membership.household_id)
    return jsonify({
        'id': household.id,
        'name': household.name,
        'role': membership.role
    })
