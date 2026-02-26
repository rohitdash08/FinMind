"""Household API routes for shared family budgeting."""
from flask import Blueprint, request, jsonify, g
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import User
from ..models_household import Household, HouseholdMember, HouseholdRole
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


def require_role(required_role: HouseholdRole):
    """Decorator to check household role permission."""
    def decorator(f):
        @wraps(f)
        @household_required
        def decorated(*args, **kwargs):
            if not g.household_member.has_permission(required_role):
                return jsonify({"error": "Insufficient permissions"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


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
        return jsonify({
            "error": "You already belong to a household. Leave it first to create a new one."
        }), 400
    
    try:
        # Create household
        household = Household(name=name, owner_id=g.user.id)
        db.session.add(household)
        db.session.flush()
        
        # Add owner as a member with OWNER role
        member = HouseholdMember(
            household_id=household.id,
            user_id=g.user.id,
            role=HouseholdRole.OWNER.value
        )
        db.session.add(member)
        db.session.commit()
        
        return jsonify({
            "message": "Household created successfully",
            "household": {
                **household.to_dict(),
                "role": HouseholdRole.OWNER.value
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to create household: {str(e)}"}), 500


@bp.route("", methods=["GET"])
def get_my_household():
    """Get the current user's household info."""
    member = HouseholdMember.query.filter_by(user_id=g.user.id).first()
    
    if not member:
        return jsonify({
            "household": None,
            "message": "You are not a member of any household"
        }), 200
    
    household = member.household
    
    return jsonify({
        "household": {
            **household.to_dict(include_members=True),
            "role": member.role
        }
    }), 200


@bp.route("/join", methods=["POST"])
def join_household():
    """Join an existing household using invite code."""
    data = request.get_json()
    invite_code = data.get("invite_code", "").strip()
    
    if not invite_code:
        return jsonify({"error": "Invite code is required"}), 400
    
    # Check if user already belongs to a household
    existing = HouseholdMember.query.filter_by(user_id=g.user.id).first()
    if existing:
        return jsonify({
            "error": "You already belong to a household. Leave it first to join another."
        }), 400
    
    # Find household by invite code
    household = Household.query.filter_by(invite_code=invite_code).first()
    if not household:
        return jsonify({"error": "Invalid invite code"}), 404
    
    try:
        # Add user as member
        member = HouseholdMember(
            household_id=household.id,
            user_id=g.user.id,
            role=HouseholdRole.MEMBER.value
        )
        db.session.add(member)
        db.session.commit()
        
        return jsonify({
            "message": "Successfully joined household",
            "household": {
                **household.to_dict(),
                "role": HouseholdRole.MEMBER.value
            }
        }), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "You are already a member of this household"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to join household: {str(e)}"}), 500


@bp.route("/leave", methods=["POST"])
@household_required
def leave_household():
    """Leave the current household."""
    member = g.household_member
    household = g.household
    
    # If owner, check if there are other members
    if member.role == HouseholdRole.OWNER.value:
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
@require_role(HouseholdRole.ADMIN)
def remove_member(user_id):
    """Remove a member from the household (admin/owner only)."""
    household = g.household
    
    target_member = HouseholdMember.query.filter_by(
        household_id=household.id,
        user_id=user_id
    ).first()
    
    if not target_member:
        return jsonify({"error": "Member not found in your household"}), 404
    
    # Can't remove the owner
    if target_member.role == HouseholdRole.OWNER.value:
        return jsonify({"error": "Cannot remove the owner"}), 400
    
    # Only owner can remove admins
    if target_member.role == HouseholdRole.ADMIN.value:
        if g.household_member.role != HouseholdRole.OWNER.value:
            return jsonify({"error": "Only the owner can remove admins"}), 403
    
    db.session.delete(target_member)
    db.session.commit()
    
    return jsonify({"message": "Member removed successfully"}), 200


@bp.route("/members/<int:user_id>/role", methods=["PATCH"])
@require_role(HouseholdRole.OWNER)
def update_member_role(user_id):
    """Update a member's role (owner only)."""
    data = request.get_json()
    new_role = data.get("role", "").upper()
    
    if new_role not in [r.value for r in HouseholdRole]:
        return jsonify({"error": "Invalid role"}), 400
    
    if new_role == HouseholdRole.OWNER.value:
        return jsonify({"error": "Cannot assign OWNER role. Use transfer ownership instead."}), 400
    
    household = g.household
    
    target_member = HouseholdMember.query.filter_by(
        household_id=household.id,
        user_id=user_id
    ).first()
    
    if not target_member:
        return jsonify({"error": "Member not found in your household"}), 404
    
    if target_member.role == HouseholdRole.OWNER.value:
        return jsonify({"error": "Cannot change owner's role"}), 400
    
    target_member.role = new_role
    db.session.commit()
    
    return jsonify({
        "message": "Member role updated successfully",
        "member": target_member.to_dict()
    }), 200


@bp.route("/transfer-ownership", methods=["POST"])
@require_role(HouseholdRole.OWNER)
def transfer_ownership():
    """Transfer household ownership to another member."""
    data = request.get_json()
    new_owner_id = data.get("user_id")
    
    if not new_owner_id:
        return jsonify({"error": "user_id is required"}), 400
    
    household = g.household
    current_owner = g.household_member
    
    # Find the new owner
    new_owner = HouseholdMember.query.filter_by(
        household_id=household.id,
        user_id=new_owner_id
    ).first()
    
    if not new_owner:
        return jsonify({"error": "User is not a member of this household"}), 404
    
    if new_owner.user_id == current_owner.user_id:
        return jsonify({"error": "You are already the owner"}), 400
    
    # Transfer ownership
    new_owner.role = HouseholdRole.OWNER.value
    current_owner.role = HouseholdRole.ADMIN.value
    household.owner_id = new_owner_id
    
    db.session.commit()
    
    return jsonify({
        "message": "Ownership transferred successfully",
        "new_owner": new_owner.to_dict()
    }), 200


@bp.route("/invite-code/regenerate", methods=["POST"])
@require_role(HouseholdRole.ADMIN)
def regenerate_invite_code():
    """Regenerate household invite code (admin/owner only)."""
    import secrets
    
    household = g.household
    household.invite_code = secrets.token_urlsafe(16)
    db.session.commit()
    
    return jsonify({
        "message": "Invite code regenerated successfully",
        "invite_code": household.invite_code
    }), 200
