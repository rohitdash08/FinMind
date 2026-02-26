"""Routes for shared household budgeting."""

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from ..extensions import db
from ..models import (
    Household,
    HouseholdBudget,
    HouseholdExpense,
    HouseholdMember,
    HouseholdRole,
)

bp = Blueprint("household", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_membership(household_id: int, user_id: int):
    return HouseholdMember.query.filter_by(
        household_id=household_id, user_id=user_id
    ).first()


def _require_role(household_id: int, user_id: int, min_roles: set[str]):
    """Return (member, error_response).  error_response is None on success."""
    member = _get_membership(household_id, user_id)
    if not member:
        return None, (jsonify(error="not a member of this household"), 403)
    if member.role not in min_roles:
        return None, (jsonify(error="insufficient permissions"), 403)
    return member, None


# ---------------------------------------------------------------------------
# Household CRUD
# ---------------------------------------------------------------------------

@bp.post("")
@jwt_required()
def create_household():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    name = data.get("name")
    if not name:
        return jsonify(error="name is required"), 400

    household = Household(name=name, created_by=uid)
    db.session.add(household)
    db.session.flush()

    owner = HouseholdMember(
        household_id=household.id, user_id=uid, role=HouseholdRole.OWNER.value
    )
    db.session.add(owner)
    db.session.commit()

    return jsonify(id=household.id, name=household.name), 201


@bp.get("")
@jwt_required()
def list_households():
    uid = int(get_jwt_identity())
    memberships = HouseholdMember.query.filter_by(user_id=uid).all()
    hids = [m.household_id for m in memberships]
    households = Household.query.filter(Household.id.in_(hids)).all() if hids else []
    return jsonify(
        households=[
            {"id": h.id, "name": h.name, "created_at": h.created_at.isoformat()}
            for h in households
        ]
    )


@bp.get("/<int:hid>")
@jwt_required()
def get_household(hid: int):
    uid = int(get_jwt_identity())
    member = _get_membership(hid, uid)
    if not member:
        return jsonify(error="not a member of this household"), 403
    h = db.session.get(Household, hid)
    if not h:
        return jsonify(error="not found"), 404
    members = HouseholdMember.query.filter_by(household_id=hid).all()
    return jsonify(
        id=h.id,
        name=h.name,
        members=[
            {"user_id": m.user_id, "role": m.role, "joined_at": m.joined_at.isoformat()}
            for m in members
        ],
    )


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------

@bp.post("/<int:hid>/members")
@jwt_required()
def add_member(hid: int):
    uid = int(get_jwt_identity())
    _, err = _require_role(hid, uid, {HouseholdRole.OWNER.value, HouseholdRole.ADMIN.value})
    if err:
        return err

    data = request.get_json() or {}
    target_uid = data.get("user_id")
    role = data.get("role", HouseholdRole.MEMBER.value)
    if not target_uid:
        return jsonify(error="user_id is required"), 400
    if role not in {r.value for r in HouseholdRole}:
        return jsonify(error="invalid role"), 400

    existing = _get_membership(hid, target_uid)
    if existing:
        return jsonify(error="user already a member"), 409

    member = HouseholdMember(household_id=hid, user_id=target_uid, role=role)
    db.session.add(member)
    db.session.commit()
    return jsonify(message="member added"), 201


@bp.delete("/<int:hid>/members/<int:member_uid>")
@jwt_required()
def remove_member(hid: int, member_uid: int):
    uid = int(get_jwt_identity())
    _, err = _require_role(hid, uid, {HouseholdRole.OWNER.value, HouseholdRole.ADMIN.value})
    if err:
        return err

    member = _get_membership(hid, member_uid)
    if not member:
        return jsonify(error="member not found"), 404
    if member.role == HouseholdRole.OWNER.value and member_uid != uid:
        return jsonify(error="cannot remove the owner"), 403

    db.session.delete(member)
    db.session.commit()
    return jsonify(message="member removed")


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

@bp.post("/<int:hid>/budgets")
@jwt_required()
def create_budget(hid: int):
    uid = int(get_jwt_identity())
    _, err = _require_role(
        hid, uid,
        {HouseholdRole.OWNER.value, HouseholdRole.ADMIN.value, HouseholdRole.MEMBER.value},
    )
    if err:
        return err

    data = request.get_json() or {}
    required = ("name", "amount_limit", "period_start", "period_end")
    if not all(data.get(k) for k in required):
        return jsonify(error=f"fields required: {', '.join(required)}"), 400

    try:
        ps = date.fromisoformat(data["period_start"])
        pe = date.fromisoformat(data["period_end"])
    except ValueError:
        return jsonify(error="invalid date format"), 400

    budget = HouseholdBudget(
        household_id=hid,
        name=data["name"],
        amount_limit=data["amount_limit"],
        period_start=ps,
        period_end=pe,
        created_by=uid,
    )
    db.session.add(budget)
    db.session.commit()
    return jsonify(id=budget.id, name=budget.name), 201


@bp.get("/<int:hid>/budgets")
@jwt_required()
def list_budgets(hid: int):
    uid = int(get_jwt_identity())
    member = _get_membership(hid, uid)
    if not member:
        return jsonify(error="not a member"), 403

    budgets = HouseholdBudget.query.filter_by(household_id=hid).all()
    result = []
    for b in budgets:
        spent = (
            db.session.query(func.coalesce(func.sum(HouseholdExpense.amount), 0))
            .filter_by(household_id=hid, budget_id=b.id)
            .scalar()
        )
        result.append({
            "id": b.id,
            "name": b.name,
            "amount_limit": float(b.amount_limit),
            "spent": float(spent),
            "remaining": float(b.amount_limit) - float(spent),
            "period_start": b.period_start.isoformat(),
            "period_end": b.period_end.isoformat(),
        })
    return jsonify(budgets=result)


# ---------------------------------------------------------------------------
# Shared expenses
# ---------------------------------------------------------------------------

@bp.post("/<int:hid>/expenses")
@jwt_required()
def add_expense(hid: int):
    uid = int(get_jwt_identity())
    member, err = _require_role(
        hid, uid,
        {HouseholdRole.OWNER.value, HouseholdRole.ADMIN.value, HouseholdRole.MEMBER.value},
    )
    if err:
        return err

    data = request.get_json() or {}
    amount = data.get("amount")
    if not amount:
        return jsonify(error="amount is required"), 400

    spent_at = date.today()
    if data.get("spent_at"):
        try:
            spent_at = date.fromisoformat(data["spent_at"])
        except ValueError:
            return jsonify(error="invalid date"), 400

    expense = HouseholdExpense(
        household_id=hid,
        budget_id=data.get("budget_id"),
        user_id=uid,
        amount=amount,
        notes=data.get("notes"),
        spent_at=spent_at,
    )
    db.session.add(expense)
    db.session.commit()
    return jsonify(id=expense.id), 201


@bp.get("/<int:hid>/expenses")
@jwt_required()
def list_expenses(hid: int):
    uid = int(get_jwt_identity())
    member = _get_membership(hid, uid)
    if not member:
        return jsonify(error="not a member"), 403

    expenses = (
        HouseholdExpense.query
        .filter_by(household_id=hid)
        .order_by(HouseholdExpense.spent_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        expenses=[
            {
                "id": e.id,
                "user_id": e.user_id,
                "amount": float(e.amount),
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat(),
                "budget_id": e.budget_id,
            }
            for e in expenses
        ]
    )
