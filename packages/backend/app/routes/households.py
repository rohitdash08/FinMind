"""Shared household budgeting routes.

Allows multiple users to collaborate on household finances by creating
households, inviting members, and sharing expenses/budgets.
"""

from datetime import datetime

from flask import Blueprint, g, jsonify, request

from ..extensions import db
from ..models import (
    AuditLog,
    Expense,
    Household,
    HouseholdBudget,
    HouseholdMember,
    HouseholdRole,
    User,
)

households_bp = Blueprint("households", __name__, url_prefix="/api/households")


def _require_membership(household_id):
    """Return the HouseholdMember row for the current user, or abort 403."""
    member = HouseholdMember.query.filter_by(
        household_id=household_id, user_id=g.user_id
    ).first()
    if not member:
        return None
    return member


def _require_admin(household_id):
    """Return the HouseholdMember row only if the user is an admin."""
    member = _require_membership(household_id)
    if not member or member.role != HouseholdRole.ADMIN:
        return None
    return member


# ── Household CRUD ──────────────────────────────────────────────


@households_bp.route("", methods=["POST"])
def create_household():
    """Create a new household. The creator becomes the admin."""
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400

    household = Household(name=name, created_by=g.user_id)
    db.session.add(household)
    db.session.flush()  # get household.id

    membership = HouseholdMember(
        household_id=household.id,
        user_id=g.user_id,
        role=HouseholdRole.ADMIN,
    )
    db.session.add(membership)
    db.session.add(
        AuditLog(user_id=g.user_id, action=f"household.create:{household.id}")
    )
    db.session.commit()

    return jsonify(id=household.id, name=household.name), 201


@households_bp.route("", methods=["GET"])
def list_households():
    """List all households the current user belongs to."""
    memberships = HouseholdMember.query.filter_by(user_id=g.user_id).all()
    household_ids = [m.household_id for m in memberships]
    households = Household.query.filter(Household.id.in_(household_ids)).all()

    return jsonify(
        [
            dict(
                id=h.id,
                name=h.name,
                role=next(
                    m.role.value for m in memberships if m.household_id == h.id
                ),
                created_at=h.created_at.isoformat(),
            )
            for h in households
        ]
    )


@households_bp.route("/<int:hid>", methods=["GET"])
def get_household(hid):
    """Get household details + members."""
    member = _require_membership(hid)
    if not member:
        return jsonify(error="Not a member of this household"), 403

    household = Household.query.get_or_404(hid)
    members = HouseholdMember.query.filter_by(household_id=hid).all()
    users = {u.id: u for u in User.query.filter(User.id.in_([m.user_id for m in members])).all()}

    return jsonify(
        id=household.id,
        name=household.name,
        members=[
            dict(
                user_id=m.user_id,
                email=users[m.user_id].email,
                role=m.role.value,
                joined_at=m.joined_at.isoformat(),
            )
            for m in members
        ],
    )


@households_bp.route("/<int:hid>", methods=["PATCH"])
def update_household(hid):
    """Update household name. Admin only."""
    admin = _require_admin(hid)
    if not admin:
        return jsonify(error="Admin access required"), 403

    data = request.get_json(force=True)
    household = Household.query.get_or_404(hid)
    if "name" in data:
        household.name = data["name"].strip()
    db.session.commit()
    return jsonify(id=household.id, name=household.name)


@households_bp.route("/<int:hid>", methods=["DELETE"])
def delete_household(hid):
    """Delete a household. Admin only."""
    admin = _require_admin(hid)
    if not admin:
        return jsonify(error="Admin access required"), 403

    HouseholdBudget.query.filter_by(household_id=hid).delete()
    HouseholdMember.query.filter_by(household_id=hid).delete()
    Household.query.filter_by(id=hid).delete()
    db.session.add(
        AuditLog(user_id=g.user_id, action=f"household.delete:{hid}")
    )
    db.session.commit()
    return "", 204


# ── Member Management ───────────────────────────────────────────


@households_bp.route("/<int:hid>/members", methods=["POST"])
def add_member(hid):
    """Invite a user to the household by email. Admin only."""
    admin = _require_admin(hid)
    if not admin:
        return jsonify(error="Admin access required"), 403

    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    role = data.get("role", "MEMBER").upper()

    if role not in ("ADMIN", "MEMBER", "VIEWER"):
        return jsonify(error="Invalid role. Use ADMIN, MEMBER, or VIEWER"), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify(error="User not found"), 404

    existing = HouseholdMember.query.filter_by(
        household_id=hid, user_id=user.id
    ).first()
    if existing:
        return jsonify(error="User is already a member"), 409

    membership = HouseholdMember(
        household_id=hid,
        user_id=user.id,
        role=HouseholdRole(role),
    )
    db.session.add(membership)
    db.session.add(
        AuditLog(
            user_id=g.user_id,
            action=f"household.add_member:{hid}:user:{user.id}",
        )
    )
    db.session.commit()
    return jsonify(user_id=user.id, role=role, household_id=hid), 201


@households_bp.route("/<int:hid>/members/<int:uid>", methods=["PATCH"])
def update_member_role(hid, uid):
    """Change a member's role. Admin only."""
    admin = _require_admin(hid)
    if not admin:
        return jsonify(error="Admin access required"), 403

    data = request.get_json(force=True)
    role = data.get("role", "").upper()
    if role not in ("ADMIN", "MEMBER", "VIEWER"):
        return jsonify(error="Invalid role"), 400

    member = HouseholdMember.query.filter_by(
        household_id=hid, user_id=uid
    ).first()
    if not member:
        return jsonify(error="Member not found"), 404

    member.role = HouseholdRole(role)
    db.session.commit()
    return jsonify(user_id=uid, role=role)


@households_bp.route("/<int:hid>/members/<int:uid>", methods=["DELETE"])
def remove_member(hid, uid):
    """Remove a member from the household. Admin only (or self-leave)."""
    member = _require_membership(hid)
    if not member:
        return jsonify(error="Not a member"), 403

    # Allow self-leave or admin removal
    if uid != g.user_id and member.role != HouseholdRole.ADMIN:
        return jsonify(error="Admin access required"), 403

    target = HouseholdMember.query.filter_by(
        household_id=hid, user_id=uid
    ).first()
    if not target:
        return jsonify(error="Member not found"), 404

    db.session.delete(target)
    db.session.add(
        AuditLog(
            user_id=g.user_id,
            action=f"household.remove_member:{hid}:user:{uid}",
        )
    )
    db.session.commit()
    return "", 204


# ── Shared Expenses ─────────────────────────────────────────────


@households_bp.route("/<int:hid>/expenses", methods=["GET"])
def list_household_expenses(hid):
    """List all expenses from all household members."""
    member = _require_membership(hid)
    if not member:
        return jsonify(error="Not a member"), 403

    member_ids = [
        m.user_id
        for m in HouseholdMember.query.filter_by(household_id=hid).all()
    ]

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)

    query = Expense.query.filter(Expense.user_id.in_(member_ids)).order_by(
        Expense.spent_at.desc()
    )

    total = query.count()
    expenses = query.offset((page - 1) * per_page).limit(per_page).all()

    users = {u.id: u.email for u in User.query.filter(User.id.in_(member_ids)).all()}

    return jsonify(
        total=total,
        page=page,
        per_page=per_page,
        expenses=[
            dict(
                id=e.id,
                user_id=e.user_id,
                user_email=users.get(e.user_id, ""),
                amount=float(e.amount),
                currency=e.currency,
                expense_type=e.expense_type,
                notes=e.notes,
                spent_at=e.spent_at.isoformat(),
                category_id=e.category_id,
            )
            for e in expenses
        ],
    )


# ── Household Budget ────────────────────────────────────────────


@households_bp.route("/<int:hid>/budgets", methods=["GET"])
def list_budgets(hid):
    """List household budgets."""
    member = _require_membership(hid)
    if not member:
        return jsonify(error="Not a member"), 403

    budgets = HouseholdBudget.query.filter_by(household_id=hid).all()
    return jsonify(
        [
            dict(
                id=b.id,
                category=b.category,
                monthly_limit=float(b.monthly_limit),
                currency=b.currency,
            )
            for b in budgets
        ]
    )


@households_bp.route("/<int:hid>/budgets", methods=["POST"])
def create_budget(hid):
    """Create a household budget category. Admin or Member."""
    member = _require_membership(hid)
    if not member or member.role == HouseholdRole.VIEWER:
        return jsonify(error="Write access required"), 403

    data = request.get_json(force=True)
    category = (data.get("category") or "").strip()
    monthly_limit = data.get("monthly_limit")

    if not category or monthly_limit is None:
        return jsonify(error="category and monthly_limit required"), 400

    budget = HouseholdBudget(
        household_id=hid,
        category=category,
        monthly_limit=monthly_limit,
        currency=data.get("currency", "INR"),
    )
    db.session.add(budget)
    db.session.commit()
    return jsonify(id=budget.id, category=budget.category, monthly_limit=float(budget.monthly_limit)), 201


@households_bp.route("/<int:hid>/budgets/<int:bid>", methods=["DELETE"])
def delete_budget(hid, bid):
    """Delete a household budget. Admin only."""
    admin = _require_admin(hid)
    if not admin:
        return jsonify(error="Admin access required"), 403

    HouseholdBudget.query.filter_by(id=bid, household_id=hid).delete()
    db.session.commit()
    return "", 204


# ── Household Summary ───────────────────────────────────────────


@households_bp.route("/<int:hid>/summary", methods=["GET"])
def household_summary(hid):
    """Get spending summary for the household (current month)."""
    member = _require_membership(hid)
    if not member:
        return jsonify(error="Not a member"), 403

    member_ids = [
        m.user_id
        for m in HouseholdMember.query.filter_by(household_id=hid).all()
    ]

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    expenses = Expense.query.filter(
        Expense.user_id.in_(member_ids),
        Expense.spent_at >= month_start.date(),
    ).all()

    total_spent = sum(float(e.amount) for e in expenses)

    # Per-member breakdown
    users = {u.id: u.email for u in User.query.filter(User.id.in_(member_ids)).all()}
    per_member = {}
    for e in expenses:
        email = users.get(e.user_id, str(e.user_id))
        per_member[email] = per_member.get(email, 0) + float(e.amount)

    # Budget comparison
    budgets = HouseholdBudget.query.filter_by(household_id=hid).all()
    budget_total = sum(float(b.monthly_limit) for b in budgets)

    return jsonify(
        month=now.strftime("%Y-%m"),
        total_spent=total_spent,
        budget_total=budget_total,
        remaining=budget_total - total_spent if budget_total > 0 else None,
        member_breakdown=per_member,
        member_count=len(member_ids),
    )
