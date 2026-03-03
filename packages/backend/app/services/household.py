"""Shared household budgeting — multi-user collaboration.

Allows users to create a household, invite members, and share
expense visibility across all household members.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Household, HouseholdMember, Expense, User, Category


def create_household(owner_id: int, name: str) -> dict:
    h = Household(name=name, owner_id=owner_id)
    db.session.add(h)
    db.session.flush()
    # Owner is automatically a member
    m = HouseholdMember(household_id=h.id, user_id=owner_id, role="owner")
    db.session.add(m)
    db.session.commit()
    return _serialize_household(h)


def get_household(user_id: int) -> dict | None:
    member = (
        db.session.query(HouseholdMember)
        .filter(HouseholdMember.user_id == user_id)
        .first()
    )
    if not member:
        return None
    h = db.session.get(Household, member.household_id)
    return _serialize_household(h) if h else None


def invite_member(owner_id: int, email: str) -> dict | None:
    """Invite a user by email to the household."""
    member = (
        db.session.query(HouseholdMember)
        .filter(HouseholdMember.user_id == owner_id, HouseholdMember.role == "owner")
        .first()
    )
    if not member:
        return None

    invitee = db.session.query(User).filter(User.email == email).first()
    if not invitee:
        return None

    existing = (
        db.session.query(HouseholdMember)
        .filter(
            HouseholdMember.household_id == member.household_id,
            HouseholdMember.user_id == invitee.id,
        )
        .first()
    )
    if existing:
        return {"error": "already_member"}

    new_member = HouseholdMember(
        household_id=member.household_id, user_id=invitee.id, role="member"
    )
    db.session.add(new_member)
    db.session.commit()

    h = db.session.get(Household, member.household_id)
    return _serialize_household(h)


def remove_member(owner_id: int, member_user_id: int) -> bool:
    owner_mem = (
        db.session.query(HouseholdMember)
        .filter(HouseholdMember.user_id == owner_id, HouseholdMember.role == "owner")
        .first()
    )
    if not owner_mem or member_user_id == owner_id:
        return False
    target = (
        db.session.query(HouseholdMember)
        .filter(
            HouseholdMember.household_id == owner_mem.household_id,
            HouseholdMember.user_id == member_user_id,
        )
        .first()
    )
    if not target:
        return False
    db.session.delete(target)
    db.session.commit()
    return True


def household_summary(user_id: int, ym: str | None = None) -> dict | None:
    """Aggregated household financial summary for a given month."""
    member = (
        db.session.query(HouseholdMember)
        .filter(HouseholdMember.user_id == user_id)
        .first()
    )
    if not member:
        return None

    ym = ym or date.today().strftime("%Y-%m")
    year, month = map(int, ym.split("-"))

    # Get all household member IDs
    members = (
        db.session.query(HouseholdMember)
        .filter(HouseholdMember.household_id == member.household_id)
        .all()
    )
    member_ids = [m.user_id for m in members]

    # Aggregate expenses
    total_income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id.in_(member_ids),
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar() or 0
    )
    total_expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id.in_(member_ids),
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar() or 0
    )

    # Per-member breakdown
    per_member = []
    for mid in member_ids:
        u = db.session.get(User, mid)
        spent = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == mid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar() or 0
        )
        per_member.append({
            "user_id": mid,
            "email": u.email if u else "?",
            "expenses": round(spent, 2),
            "share_pct": round((spent / total_expenses) * 100, 2) if total_expenses > 0 else 0,
        })

    h = db.session.get(Household, member.household_id)
    return {
        "household": h.name if h else "?",
        "month": ym,
        "member_count": len(member_ids),
        "total_income": round(total_income, 2),
        "total_expenses": round(total_expenses, 2),
        "net_flow": round(total_income - total_expenses, 2),
        "per_member": per_member,
    }


def _serialize_household(h: Household) -> dict:
    members = (
        db.session.query(HouseholdMember, User)
        .join(User, HouseholdMember.user_id == User.id)
        .filter(HouseholdMember.household_id == h.id)
        .all()
    )
    return {
        "id": h.id,
        "name": h.name,
        "owner_id": h.owner_id,
        "members": [
            {"user_id": m.user_id, "email": u.email, "role": m.role}
            for m, u in members
        ],
        "created_at": h.created_at.isoformat(),
    }
