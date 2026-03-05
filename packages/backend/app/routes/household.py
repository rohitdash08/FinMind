from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Household, HouseholdMember, User

household_bp = Blueprint("household", __name__)


@household_bp.route("/households", methods=["GET"])
@login_required
def get_households():
    """Get all households the current user is a member of."""
    memberships = HouseholdMember.query.filter_by(user_id=current_user.id).all()
    households = []
    for m in memberships:
        h = m.household
        households.append({
            "id": h.id,
            "name": h.name,
            "role": m.role,
            "joined_at": h.joined_at.isoformat() if h.joined_at else None,
            "members_count": len(h.members)
        })
    return jsonify(households)


@household_bp.route("/households", methods=["POST"])
@login_required
def create_household():
    """Create a new household."""
    data = request.get_json()
    name = data.get("name")
    
    if not name:
        return jsonify({"error": "Household name is required"}), 400
    
    household = Household(name=name, created_by=current_user.id)
    db.session.add(household)
    db.session.flush()
    
    # Add creator as owner
    member = HouseholdMember(
        household_id=household.id,
        user_id=current_user.id,
        role="owner"
    )
    db.session.add(member)
    db.session.commit()
    
    return jsonify({
        "id": household.id,
        "name": household.name,
        "role": "owner",
        "created_at": household.created_at.isoformat()
    }), 201


@household_bp.route("/households/<int:household_id>", methods=["GET"])
@login_required
def get_household(household_id):
    """Get household details."""
    member = HouseholdMember.query.filter_by(
        household_id=household_id, 
        user_id=current_user.id
    ).first()
    
    if not member:
        return jsonify({"error": "Not a member of this household"}), 403
    
    household = member.household
    members = []
    for m in household.members:
        members.append({
            "id": m.id,
            "user_id": m.user_id,
            "email": m.user.email if m.user else None,
            "role": m.role,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None
        })
    
    return jsonify({
        "id": household.id,
        "name": household.name,
        "role": member.role,
        "created_by": household.created_by,
        "members": members
    })


@household_bp.route("/households/<int:household_id>/join", methods=["POST"])
@login_required
def join_household(household_id):
    """Join a household by invite code or email."""
    data = request.get_json()
    email = data.get("email")
    
    # For now, any user can join if they know the household ID
    # In production, this would use invite codes
    member = HouseholdMember.query.filter_by(
        household_id=household_id,
        user_id=current_user.id
    ).first()
    
    if member:
        return jsonify({"error": "Already a member"}), 400
    
    household = Household.query.get(household_id)
    if not household:
        return jsonify({"error": "Household not found"}), 404
    
    new_member = HouseholdMember(
        household_id=household_id,
        user_id=current_user.id,
        role="member"
    )
    db.session.add(new_member)
    db.session.commit()
    
    return jsonify({
        "id": household.id,
        "name": household.name,
        "role": "member"
    }), 201


@household_bp.route("/households/<int:household_id>/members", methods=["POST"])
@login_required
def add_member(household_id):
    """Add a member to household (owner only)."""
    member = HouseholdMember.query.filter_by(
        household_id=household_id, 
        user_id=current_user.id
    ).first()
    
    if not member or member.role != "owner":
        return jsonify({"error": "Only owners can add members"}), 403
    
    data = request.get_json()
    email = data.get("email")
    
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    existing = HouseholdMember.query.filter_by(
        household_id=household_id,
        user_id=user.id
    ).first()
    
    if existing:
        return jsonify({"error": "User already a member"}), 400
    
    new_member = HouseholdMember(
        household_id=household_id,
        user_id=user.id,
        role="member"
    )
    db.session.add(new_member)
    db.session.commit()
    
    return jsonify({
        "user_id": user.id,
        "email": user.email,
        "role": "member"
    }), 201


@household_bp.route("/households/<int:household_id>/leave", methods=["POST"])
@login_required
def leave_household(household_id):
    """Leave a household."""
    member = HouseholdMember.query.filter_by(
        household_id=household_id, 
        user_id=current_user.id
    ).first()
    
    if not member:
        return jsonify({"error": "Not a member"}), 404
    
    if member.role == "owner" and len(member.household.members) > 1:
        return jsonify({"error": "Owner must transfer ownership before leaving"}), 400
    
    db.session.delete(member)
    db.session.commit()
    
    return jsonify({"message": "Left household successfully"})
