"""Household budgeting routes — create, invite, join, view shared expenses."""

import secrets
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import (
    Household, HouseholdMember, HouseholdInvite, HouseholdRole,
    User, Expense,
)
import logging

bp = Blueprint("household", __name__)
logger = logging.getLogger("finmind.household")


# ── helpers ──────────────────────────────────────────────────────────────────

def _serialize_household(h: Household, members=None) -> dict:
    return {
        "id": h.id,
        "name": h.name,
        "owner_id": h.owner_id,
        "created_at": h.created_at.isoformat(),
        "members": [
            {
                "user_id": m.user_id,
                "role": m.role,
                "joined_at": m.joined_at.isoformat(),
            }
            for m in (members or h.members.all())
        ],
    }


def _is_member(household_id: int, user_id: int) -> bool:
    return HouseholdMember.query.filter_by(
        household_id=household_id, user_id=user_id
    ).first() is not None


# ── CRUD ─────────────────────────────────────────────────────────────────────

@bp.post("")
@jwt_required()
def create_household():
    """Create a new household. The creator becomes the owner."""
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    household = Household(name=name, owner_id=uid)
    db.session.add(household)
    db.session.flush()

    member = HouseholdMember(
        household_id=household.id, user_id=uid, role=HouseholdRole.OWNER.value
    )
    db.session.add(member)
    db.session.commit()

    logger.info("Household created id=%s by user=%s", household.id, uid)
    return jsonify(_serialize_household(household)), 201


@bp.get("")
@jwt_required()
def list_households():
    """List all households the current user belongs to."""
    uid = int(get_jwt_identity())
    memberships = HouseholdMember.query.filter_by(user_id=uid).all()
    households = [
        _serialize_household(Household.query.get(m.household_id))
        for m in memberships
    ]
    return jsonify(households)


@bp.get("/<int:household_id>")
@jwt_required()
def get_household(household_id: int):
    """Get household details (members only)."""
    uid = int(get_jwt_identity())
    if not _is_member(household_id, uid):
        return jsonify({"error": "not a member"}), 403
    household = Household.query.get_or_404(household_id)
    return jsonify(_serialize_household(household))


@bp.delete("/<int:household_id>")
@jwt_required()
def delete_household(household_id: int):
    """Delete a household (owner only)."""
    uid = int(get_jwt_identity())
    household = Household.query.get_or_404(household_id)
    if household.owner_id != uid:
        return jsonify({"error": "only the owner can delete"}), 403

    HouseholdInvite.query.filter_by(household_id=household_id).delete()
    HouseholdMember.query.filter_by(household_id=household_id).delete()
    db.session.delete(household)
    db.session.commit()
    return jsonify({"message": "deleted"})


# ── Invites ──────────────────────────────────────────────────────────────────

@bp.post("/<int:household_id>/invite")
@jwt_required()
def invite_member(household_id: int):
    """Invite a user by email to a household."""
    uid = int(get_jwt_identity())
    if not _is_member(household_id, uid):
        return jsonify({"error": "not a member"}), 403

    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    token = secrets.token_urlsafe(32)
    invite = HouseholdInvite(
        household_id=household_id, email=email, invited_by=uid, token=token
    )
    db.session.add(invite)
    db.session.commit()

    logger.info("Invite sent household=%s email=%s by user=%s", household_id, email, uid)
    return jsonify({"token": token, "email": email}), 201


@bp.post("/join")
@jwt_required()
def join_household():
    """Accept an invite using a token."""
    uid = int(get_jwt_identity())
    data = request.get_json(force=True)
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token is required"}), 400

    invite = HouseholdInvite.query.filter_by(token=token, accepted=False).first()
    if not invite:
        return jsonify({"error": "invalid or already used invite"}), 404

    user = User.query.get(uid)
    if user.email.lower() != invite.email.lower():
        return jsonify({"error": "invite is for a different email"}), 403

    if _is_member(invite.household_id, uid):
        return jsonify({"error": "already a member"}), 409

    member = HouseholdMember(
        household_id=invite.household_id, user_id=uid, role=HouseholdRole.MEMBER.value
    )
    db.session.add(member)
    invite.accepted = True
    db.session.commit()

    household = Household.query.get(invite.household_id)
    return jsonify(_serialize_household(household)), 200


# ── Shared expenses ─────────────────────────────────────────────────────────

@bp.get("/<int:household_id>/expenses")
@jwt_required()
def household_expenses(household_id: int):
    """View all expenses from household members (aggregated view)."""
    uid = int(get_jwt_identity())
    if not _is_member(household_id, uid):
        return jsonify({"error": "not a member"}), 403

    member_ids = [
        m.user_id
        for m in HouseholdMember.query.filter_by(household_id=household_id).all()
    ]

    from_date = request.args.get("from")
    to_date = request.args.get("to")

    query = Expense.query.filter(Expense.user_id.in_(member_ids))
    if from_date:
        query = query.filter(Expense.spent_at >= from_date)
    if to_date:
        query = query.filter(Expense.spent_at <= to_date)

    expenses = query.order_by(Expense.spent_at.desc()).limit(200).all()

    return jsonify([
        {
            "id": e.id,
            "user_id": e.user_id,
            "amount": float(e.amount),
            "currency": e.currency,
            "expense_type": e.expense_type,
            "notes": e.notes,
            "date": str(e.spent_at),
        }
        for e in expenses
    ])
