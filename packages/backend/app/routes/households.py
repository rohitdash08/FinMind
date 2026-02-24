"""Shared household budgeting routes.

Allows multiple users to collaborate on household finances through
shared expense tracking, budget management, and member invitations.
"""

from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import (
    Household,
    HouseholdExpense,
    HouseholdInvite,
    HouseholdMember,
    HouseholdRole,
    User,
)

bp = Blueprint("households", __name__)


def _get_membership(household_id: int, user_id: int) -> HouseholdMember | None:
    return db.session.query(HouseholdMember).filter_by(
        household_id=household_id, user_id=user_id
    ).first()


def _require_member(household_id: int, user_id: int) -> HouseholdMember | None:
    """Return membership or None (caller should return 403)."""
    return _get_membership(household_id, user_id)


def _require_owner(household_id: int, user_id: int) -> bool:
    m = _get_membership(household_id, user_id)
    return m is not None and m.role == HouseholdRole.OWNER.value


# --- Household CRUD ---


@bp.post("")
@jwt_required()
def create_household():
    """Create a new household. Creator becomes OWNER."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    household = Household(
        name=name,
        currency=data.get("currency", "INR"),
        monthly_budget=data.get("monthly_budget"),
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

    return jsonify(
        id=household.id,
        name=household.name,
        currency=household.currency,
        monthly_budget=str(household.monthly_budget) if household.monthly_budget else None,
        role=HouseholdRole.OWNER.value,
    ), 201


@bp.get("")
@jwt_required()
def list_households():
    """List all households the user belongs to."""
    uid = int(get_jwt_identity())
    memberships = (
        db.session.query(HouseholdMember, Household)
        .join(Household, Household.id == HouseholdMember.household_id)
        .filter(HouseholdMember.user_id == uid)
        .all()
    )
    return jsonify(
        households=[
            {
                "id": h.id,
                "name": h.name,
                "currency": h.currency,
                "monthly_budget": str(h.monthly_budget) if h.monthly_budget else None,
                "role": m.role,
            }
            for m, h in memberships
        ]
    )


@bp.get("/<int:hid>")
@jwt_required()
def get_household(hid: int):
    """Get household details with members and budget summary."""
    uid = int(get_jwt_identity())
    if not _require_member(hid, uid):
        return jsonify(error="not a member of this household"), 403

    household = db.session.get(Household, hid)
    if not household:
        return jsonify(error="household not found"), 404

    members = (
        db.session.query(HouseholdMember, User)
        .join(User, User.id == HouseholdMember.user_id)
        .filter(HouseholdMember.household_id == hid)
        .all()
    )

    # Monthly spend summary
    today = date.today()
    month_start = today.replace(day=1)
    month_total = (
        db.session.query(db.func.coalesce(db.func.sum(HouseholdExpense.amount), 0))
        .filter(
            HouseholdExpense.household_id == hid,
            HouseholdExpense.spent_at >= month_start,
        )
        .scalar()
    )

    return jsonify(
        id=household.id,
        name=household.name,
        currency=household.currency,
        monthly_budget=str(household.monthly_budget) if household.monthly_budget else None,
        month_spent=str(month_total),
        members=[
            {
                "user_id": u.id,
                "email": u.email,
                "role": m.role,
                "joined_at": m.joined_at.isoformat() + "Z",
            }
            for m, u in members
        ],
    )


@bp.patch("/<int:hid>")
@jwt_required()
def update_household(hid: int):
    """Update household name or budget. Owner only."""
    uid = int(get_jwt_identity())
    if not _require_owner(hid, uid):
        return jsonify(error="owner access required"), 403

    household = db.session.get(Household, hid)
    if not household:
        return jsonify(error="household not found"), 404

    data = request.get_json() or {}
    if "name" in data:
        household.name = data["name"]
    if "monthly_budget" in data:
        household.monthly_budget = data["monthly_budget"]
    if "currency" in data:
        household.currency = data["currency"]
    db.session.commit()

    return jsonify(
        id=household.id,
        name=household.name,
        currency=household.currency,
        monthly_budget=str(household.monthly_budget) if household.monthly_budget else None,
    )


# --- Invitations ---


@bp.post("/<int:hid>/invite")
@jwt_required()
def invite_member(hid: int):
    """Invite a user by email. Owner or member can invite."""
    uid = int(get_jwt_identity())
    if not _require_member(hid, uid):
        return jsonify(error="not a member of this household"), 403

    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify(error="email is required"), 400

    # Check if already a member
    target_user = db.session.query(User).filter_by(email=email).first()
    if target_user and _get_membership(hid, target_user.id):
        return jsonify(error="user is already a member"), 409

    # Check duplicate invite
    existing = db.session.query(HouseholdInvite).filter_by(
        household_id=hid, email=email, accepted=False
    ).first()
    if existing:
        return jsonify(error="invite already pending"), 409

    invite = HouseholdInvite(
        household_id=hid,
        email=email,
        invited_by=uid,
    )
    db.session.add(invite)
    db.session.commit()
    return jsonify(id=invite.id, email=email, status="pending"), 201


@bp.get("/invites")
@jwt_required()
def list_invites():
    """List pending invites for the current user."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    invites = (
        db.session.query(HouseholdInvite, Household)
        .join(Household, Household.id == HouseholdInvite.household_id)
        .filter(
            HouseholdInvite.email == user.email,
            HouseholdInvite.accepted.is_(False),
        )
        .all()
    )
    return jsonify(
        invites=[
            {
                "id": inv.id,
                "household_id": h.id,
                "household_name": h.name,
                "created_at": inv.created_at.isoformat() + "Z",
            }
            for inv, h in invites
        ]
    )


@bp.post("/invites/<int:invite_id>/accept")
@jwt_required()
def accept_invite(invite_id: int):
    """Accept a household invitation."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    invite = db.session.get(HouseholdInvite, invite_id)

    if not invite or invite.email != user.email or invite.accepted:
        return jsonify(error="invite not found"), 404

    invite.accepted = True
    member = HouseholdMember(
        household_id=invite.household_id,
        user_id=uid,
        role=HouseholdRole.MEMBER.value,
    )
    db.session.add(member)
    db.session.commit()
    return jsonify(message="joined household", household_id=invite.household_id)


@bp.post("/invites/<int:invite_id>/decline")
@jwt_required()
def decline_invite(invite_id: int):
    """Decline a household invitation."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    invite = db.session.get(HouseholdInvite, invite_id)

    if not invite or invite.email != user.email or invite.accepted:
        return jsonify(error="invite not found"), 404

    db.session.delete(invite)
    db.session.commit()
    return jsonify(message="invite declined")


# --- Household Expenses ---


@bp.post("/<int:hid>/expenses")
@jwt_required()
def add_household_expense(hid: int):
    """Add a shared expense to the household."""
    uid = int(get_jwt_identity())
    if not _require_member(hid, uid):
        return jsonify(error="not a member of this household"), 403

    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount or Decimal(str(amount)) <= 0:
        return jsonify(error="valid amount is required"), 400

    expense = HouseholdExpense(
        household_id=hid,
        paid_by=uid,
        category_id=data.get("category_id"),
        amount=Decimal(str(amount)),
        currency=data.get("currency", "INR"),
        notes=data.get("notes"),
        spent_at=date.fromisoformat(data["spent_at"]) if data.get("spent_at") else date.today(),
    )
    db.session.add(expense)
    db.session.commit()

    return jsonify(
        id=expense.id,
        household_id=hid,
        paid_by=uid,
        amount=str(expense.amount),
        notes=expense.notes,
        spent_at=expense.spent_at.isoformat(),
    ), 201


@bp.get("/<int:hid>/expenses")
@jwt_required()
def list_household_expenses(hid: int):
    """List expenses for a household with optional date filters."""
    uid = int(get_jwt_identity())
    if not _require_member(hid, uid):
        return jsonify(error="not a member of this household"), 403

    query = db.session.query(HouseholdExpense, User).join(
        User, User.id == HouseholdExpense.paid_by
    ).filter(HouseholdExpense.household_id == hid)

    from_date = request.args.get("from")
    to_date = request.args.get("to")
    if from_date:
        query = query.filter(HouseholdExpense.spent_at >= from_date)
    if to_date:
        query = query.filter(HouseholdExpense.spent_at <= to_date)

    limit = request.args.get("limit", 50, type=int)
    expenses = query.order_by(HouseholdExpense.spent_at.desc()).limit(min(limit, 200)).all()

    return jsonify(
        expenses=[
            {
                "id": e.id,
                "paid_by": u.email,
                "paid_by_id": u.id,
                "amount": str(e.amount),
                "currency": e.currency,
                "notes": e.notes,
                "category_id": e.category_id,
                "spent_at": e.spent_at.isoformat(),
            }
            for e, u in expenses
        ]
    )


@bp.get("/<int:hid>/summary")
@jwt_required()
def household_summary(hid: int):
    """Get spending summary per member for the current month."""
    uid = int(get_jwt_identity())
    if not _require_member(hid, uid):
        return jsonify(error="not a member of this household"), 403

    household = db.session.get(Household, hid)
    today = date.today()
    month_start = today.replace(day=1)

    # Per-member totals
    member_totals = (
        db.session.query(
            User.email,
            User.id,
            db.func.coalesce(db.func.sum(HouseholdExpense.amount), 0),
        )
        .join(HouseholdMember, HouseholdMember.user_id == User.id)
        .outerjoin(
            HouseholdExpense,
            db.and_(
                HouseholdExpense.paid_by == User.id,
                HouseholdExpense.household_id == hid,
                HouseholdExpense.spent_at >= month_start,
            ),
        )
        .filter(HouseholdMember.household_id == hid)
        .group_by(User.id, User.email)
        .all()
    )

    total_spent = sum(float(row[2]) for row in member_totals)
    budget = float(household.monthly_budget) if household.monthly_budget else None

    return jsonify(
        household_id=hid,
        month=today.strftime("%Y-%m"),
        total_spent=f"{total_spent:.2f}",
        monthly_budget=str(household.monthly_budget) if household.monthly_budget else None,
        remaining=f"{budget - total_spent:.2f}" if budget else None,
        per_member=[
            {
                "user_id": row[1],
                "email": row[0],
                "spent": f"{float(row[2]):.2f}",
            }
            for row in member_totals
        ],
    )


# --- Remove Member / Leave ---


@bp.post("/<int:hid>/leave")
@jwt_required()
def leave_household(hid: int):
    """Leave a household. Owner cannot leave (must transfer ownership first)."""
    uid = int(get_jwt_identity())
    member = _get_membership(hid, uid)
    if not member:
        return jsonify(error="not a member"), 404
    if member.role == HouseholdRole.OWNER.value:
        return jsonify(error="owner cannot leave — transfer ownership first"), 400
    db.session.delete(member)
    db.session.commit()
    return jsonify(message="left household")


@bp.delete("/<int:hid>/members/<int:target_uid>")
@jwt_required()
def remove_member(hid: int, target_uid: int):
    """Remove a member from the household. Owner only."""
    uid = int(get_jwt_identity())
    if not _require_owner(hid, uid):
        return jsonify(error="owner access required"), 403
    if target_uid == uid:
        return jsonify(error="cannot remove yourself — use /leave"), 400

    member = _get_membership(hid, target_uid)
    if not member:
        return jsonify(error="user is not a member"), 404
    db.session.delete(member)
    db.session.commit()
    return jsonify(message="member removed")
