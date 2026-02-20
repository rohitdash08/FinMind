"""Shared household budgeting routes.

Allows multiple users to collaborate on household finances by creating
a household, inviting members, and sharing expenses.
"""

import secrets
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import (
    Expense,
    Household,
    HouseholdMember,
    HouseholdRole,
    User,
)

bp = Blueprint("household", __name__)


def _get_user_membership(uid: int) -> HouseholdMember | None:
    return db.session.query(HouseholdMember).filter_by(user_id=uid).first()


@bp.post("")
@jwt_required()
def create_household():
    """Create a new household. User becomes owner."""
    uid = int(get_jwt_identity())
    existing = _get_user_membership(uid)
    if existing:
        return jsonify(error="already in a household"), 409
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400

    household = Household(
        name=name,
        invite_code=secrets.token_urlsafe(16),
        created_by=uid,
    )
    db.session.add(household)
    db.session.flush()

    member = HouseholdMember(
        household_id=household.id,
        user_id=uid,
        role=HouseholdRole.OWNER.value,
    )
    db.session.add(member)
    db.session.commit()
    return jsonify(_household_to_dict(household)), 201


@bp.get("")
@jwt_required()
def get_household():
    """Get user's current household."""
    uid = int(get_jwt_identity())
    membership = _get_user_membership(uid)
    if not membership:
        return jsonify(error="not in a household"), 404
    household = db.session.get(Household, membership.household_id)
    return jsonify(_household_to_dict(household))


@bp.post("/invite")
@jwt_required()
def invite_member():
    """Return invite code. Only owner can invite."""
    uid = int(get_jwt_identity())
    membership = _get_user_membership(uid)
    if not membership or membership.role != HouseholdRole.OWNER.value:
        return jsonify(error="only household owner can invite"), 403
    household = db.session.get(Household, membership.household_id)
    return jsonify(invite_code=household.invite_code)


@bp.post("/join/<code>")
@jwt_required()
def join_household(code: str):
    """Join a household via invite code."""
    uid = int(get_jwt_identity())
    existing = _get_user_membership(uid)
    if existing:
        return jsonify(error="already in a household"), 409
    household = db.session.query(Household).filter_by(invite_code=code).first()
    if not household:
        return jsonify(error="invalid invite code"), 404
    member = HouseholdMember(
        household_id=household.id,
        user_id=uid,
        role=HouseholdRole.MEMBER.value,
    )
    db.session.add(member)
    db.session.commit()
    return jsonify(_household_to_dict(household)), 200


@bp.get("/members")
@jwt_required()
def list_members():
    """List household members."""
    uid = int(get_jwt_identity())
    membership = _get_user_membership(uid)
    if not membership:
        return jsonify(error="not in a household"), 404
    members = (
        db.session.query(HouseholdMember, User)
        .join(User, HouseholdMember.user_id == User.id)
        .filter(HouseholdMember.household_id == membership.household_id)
        .all()
    )
    return jsonify([
        {
            "user_id": m.user_id,
            "email": u.email,
            "role": m.role,
            "joined_at": m.joined_at.isoformat(),
        }
        for m, u in members
    ])


@bp.get("/expenses")
@jwt_required()
def household_expenses():
    """List all expenses tagged with the user's household."""
    uid = int(get_jwt_identity())
    membership = _get_user_membership(uid)
    if not membership:
        return jsonify(error="not in a household"), 404
    expenses = (
        db.session.query(Expense)
        .filter_by(household_id=membership.household_id)
        .order_by(Expense.spent_at.desc())
        .limit(200)
        .all()
    )
    return jsonify([
        {
            "id": e.id,
            "user_id": e.user_id,
            "amount": float(e.amount),
            "currency": e.currency,
            "category_id": e.category_id,
            "expense_type": e.expense_type,
            "description": e.notes or "",
            "date": e.spent_at.isoformat(),
            "household_id": e.household_id,
        }
        for e in expenses
    ])


def _household_to_dict(h: Household) -> dict:
    return {
        "id": h.id,
        "name": h.name,
        "invite_code": h.invite_code,
        "created_by": h.created_by,
        "created_at": h.created_at.isoformat(),
    }
