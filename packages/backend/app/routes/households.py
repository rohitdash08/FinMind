"""Household API routes for shared family budgeting."""
from flask import Blueprint, request, jsonify, g
from ..extensions import db
from ..models import User
from ..models_household import Household, HouseholdMember
from functools import wraps

bp = Blueprint("households", __name__, url_prefix="/households")


def household_required(f):
    """Decorator to check if user belongs to a household."""
    @wraps(f)
    def decorated(*args, **kwargs):
        member = HouseholdMember.query.filter_by(user_id=g.user.id).first()
        if not member:
            return jsonify({"error": "You are not a member of any household"}), 400
        g.household_member = member
        g.household = member.household
        return f(*args, **kwargs)
    return decorated


@bp.route("", methods=["POST"])
def create_household():
    """Create a new household group."""
    data = request.get_json()
    name = data.get("name", "").strip()
    
    if not name:
        return jsonify({"error": "Household name is required"}), 400
    
    if len(name) > 200:
        return jsonify({"error": "Household name must be 200 characters or less"}), 400
    
    # Check if user already belongs to a household
    existing = HouseholdMember.query.filter_by(user_id=g.user.id).first()
    if existing:
        return jsonify({"error": "You already belong to a household. Leave it first to create a new one."}), 400
    
    # Create household
    household = Household(name=name, owner_id=g.user.id)
    db.session.add(household)
    db.session.flush()  # Get the ID
    
    # Add owner as a member with OWNER role
    member = HouseholdMember(
        household_id=household.id,
        user_id=g.user.id,
        role="OWNER"
    )
    db.session.add(member)
    db.session.commit()
    
    return jsonify({
        "message": "Household created successfully",
        "household": {
            "id": household.id,
            "name": household.name,
            "owner_id": household.owner_id,
            "role": "OWNER",
            "created_at": household.created_at.isoformat()
        }
    }), 201


@bp.route("", methods=["GET"])
def get_my_household():
    """Get the current user's household info."""
    member = HouseholdMember.query.filter_by(user_id=g.user.id).first()
    
    if not member:
        return jsonify({"household": None, "message": "You are not a member of any household"}), 200
    
    household = member.household
    members = HouseholdMember.query.filter_by(household_id=household.id).all()
    
    return jsonify({
        "household": {
            "id": household.id,
            "name": household.name,
            "owner_id": household.owner_id,
            "role": member.role,
            "created_at": household.created_at.isoformat(),
            "members": [{
                "id": m.id,
                "user_id": m.user_id,
                "email": m.user.email,
                "role": m.role,
                "joined_at": m.joined_at.isoformat()
            } for m in members]
        }
    }), 200


@bp.route("/join", methods=["POST"])
def join_household():
    """Join an existing household using invite code (household ID for simplicity)."""
    data = request.get_json()
    household_id = data.get("household_id")
    
    if not household_id:
        return jsonify({"error": "Household ID is required"}), 400
    
    # Check if user already belongs to a household
    existing = HouseholdMember.query.filter_by(user_id=g.user.id).first()
    if existing:
        return jsonify({"error": "You already belong to a household. Leave it first to join another."}), 400
    
    # Find the household
    household = Household.query.get(household_id)
    if not household:
        return jsonify({"error": "Household not found"}), 404
    
    # Add user as member
    member = HouseholdMember(
        household_id=household.id,
        user_id=g.user.id,
        role="MEMBER"
    )
    db.session.add(member)
    db.session.commit()
    
    return jsonify({
        "message": "Successfully joined household",
        "household": {
            "id": household.id,
            "name": household.name,
            "role": "MEMBER"
        }
    }), 200


@bp.route("/leave", methods=["POST"])
def leave_household():
    """Leave the current household."""
    member = HouseholdMember.query.filter_by(user_id=g.user.id).first()
    
    if not member:
        return jsonify({"error": "You are not a member of any household"}), 400
    
    household = member.household
    
    # Check if user is the owner
    if member.role == "OWNER":
        # Check if there are other members
        other_members = HouseholdMember.query.filter(
            HouseholdMember.household_id == household.id,
            HouseholdMember.user_id != g.user.id
        ).count()
        
        if other_members > 0:
            return jsonify({
                "error": "You are the owner. Transfer ownership or remove all members before leaving."
            }), 400
        
        # Delete the household if owner is the only member
        db.session.delete(household)
    else:
        db.session.delete(member)
    
    db.session.commit()
    
    return jsonify({"message": "Successfully left household"}), 200


@bp.route("/members/<int:user_id>", methods=["DELETE"])
def remove_member(user_id):
    """Remove a member from the household (admin/owner only)."""
    current_member = HouseholdMember.query.filter_by(user_id=g.user.id).first()
    
    if not current_member:
        return jsonify({"error": "You are not a member of any household"}), 400
    
    if current_member.role not in ["OWNER", "ADMIN"]:
        return jsonify({"error": "Only owners and admins can remove members"}), 403
    
    target_member = HouseholdMember.query.filter_by(
        household_id=current_member.household_id,
        user_id=user_id
    ).first()
    
    if not target_member:
        return jsonify({"error": "Member not found in your household"}), 404
    
    # Can't remove the owner
    if target_member.role == "OWNER":
        return jsonify({"error": "Cannot remove the owner"}), 400
    
    db.session.delete(target_member)
    db.session.commit()
    
    return jsonify({"message": "Member removed successfully"}), 200
