"""Household collaborative budgeting service.

Allows multiple users to form a household, share expenses,
set joint budgets, and track spending together.
"""

from datetime import datetime, date
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category, User


class Household(db.Model):
    __tablename__ = "households"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    members = db.relationship("HouseholdMember", backref="household", lazy=True, cascade="all, delete-orphan")
    budgets = db.relationship("HouseholdBudget", backref="household", lazy=True, cascade="all, delete-orphan")


class HouseholdMember(db.Model):
    __tablename__ = "household_members"
    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("households.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(20), default="member", nullable=False)  # owner, member
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("household_id", "user_id"),)


class HouseholdBudget(db.Model):
    __tablename__ = "household_budgets"
    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("households.id"), nullable=False)
    category_name = db.Column(db.String(100), nullable=False)
    monthly_limit = db.Column(db.Numeric(14, 2), nullable=False)
    month = db.Column(db.String(7), nullable=False)  # YYYY-MM
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def create_household(owner_id: int, name: str) -> dict:
    h = Household(name=name, owner_id=owner_id)
    db.session.add(h)
    db.session.flush()
    m = HouseholdMember(household_id=h.id, user_id=owner_id, role="owner")
    db.session.add(m)
    db.session.commit()
    return _serialize_household(h)


def get_user_households(user_id: int) -> list[dict]:
    member_rows = HouseholdMember.query.filter_by(user_id=user_id).all()
    hids = [m.household_id for m in member_rows]
    if not hids:
        return []
    households = Household.query.filter(Household.id.in_(hids)).all()
    return [_serialize_household(h) for h in households]


def get_household(user_id: int, household_id: int) -> dict | None:
    if not _is_member(user_id, household_id):
        return None
    h = Household.query.get(household_id)
    return _serialize_household(h) if h else None


def add_member(owner_id: int, household_id: int, user_email: str) -> dict | None:
    h = Household.query.get(household_id)
    if not h or h.owner_id != owner_id:
        return None
    user = User.query.filter_by(email=user_email).first()
    if not user:
        return None
    existing = HouseholdMember.query.filter_by(household_id=household_id, user_id=user.id).first()
    if existing:
        return _serialize_household(h)
    m = HouseholdMember(household_id=household_id, user_id=user.id, role="member")
    db.session.add(m)
    db.session.commit()
    return _serialize_household(h)


def remove_member(owner_id: int, household_id: int, member_user_id: int) -> bool:
    h = Household.query.get(household_id)
    if not h or h.owner_id != owner_id:
        return False
    if member_user_id == owner_id:
        return False  # can't remove owner
    m = HouseholdMember.query.filter_by(household_id=household_id, user_id=member_user_id).first()
    if not m:
        return False
    db.session.delete(m)
    db.session.commit()
    return True


def set_budget(user_id: int, household_id: int, category_name: str,
               monthly_limit: float, month: str | None = None) -> dict | None:
    if not _is_member(user_id, household_id):
        return None
    if monthly_limit <= 0:
        raise ValueError("monthly_limit must be positive")
    month = month or date.today().strftime("%Y-%m")
    existing = HouseholdBudget.query.filter_by(
        household_id=household_id, category_name=category_name, month=month
    ).first()
    if existing:
        existing.monthly_limit = monthly_limit
    else:
        b = HouseholdBudget(
            household_id=household_id, category_name=category_name,
            monthly_limit=monthly_limit, month=month,
        )
        db.session.add(b)
    db.session.commit()
    return get_budget_summary(user_id, household_id, month)


def get_budget_summary(user_id: int, household_id: int, month: str | None = None) -> dict | None:
    if not _is_member(user_id, household_id):
        return None
    month = month or date.today().strftime("%Y-%m")
    h = Household.query.get(household_id)
    member_ids = [m.user_id for m in h.members]

    budgets = HouseholdBudget.query.filter_by(household_id=household_id, month=month).all()

    # Get actual spending by all members
    year, mo = int(month[:4]), int(month[5:7])
    spending = (
        db.session.query(Category.name, func.sum(Expense.amount))
        .join(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id.in_(member_ids),
            func.extract("year", Expense.date) == year,
            func.extract("month", Expense.date) == mo,
        )
        .group_by(Category.name)
        .all()
    )
    spending_map = {name: float(total) for name, total in spending}

    budget_items = []
    for b in budgets:
        spent = spending_map.get(b.category_name, 0)
        limit = float(b.monthly_limit)
        budget_items.append({
            "category": b.category_name,
            "limit": limit,
            "spent": round(spent, 2),
            "remaining": round(limit - spent, 2),
            "pct_used": round(spent / limit * 100, 1) if limit > 0 else 0,
        })

    total_limit = sum(float(b.monthly_limit) for b in budgets)
    total_spent = sum(i["spent"] for i in budget_items)

    return {
        "household_id": household_id,
        "month": month,
        "total_budget": round(total_limit, 2),
        "total_spent": round(total_spent, 2),
        "total_remaining": round(total_limit - total_spent, 2),
        "categories": budget_items,
        "member_count": len(member_ids),
    }


def delete_household(owner_id: int, household_id: int) -> bool:
    h = Household.query.get(household_id)
    if not h or h.owner_id != owner_id:
        return False
    db.session.delete(h)
    db.session.commit()
    return True


def _is_member(user_id: int, household_id: int) -> bool:
    return HouseholdMember.query.filter_by(
        household_id=household_id, user_id=user_id
    ).first() is not None


def _serialize_household(h: Household) -> dict:
    return {
        "id": h.id,
        "name": h.name,
        "owner_id": h.owner_id,
        "members": [
            {"user_id": m.user_id, "role": m.role, "joined_at": m.joined_at.isoformat()}
            for m in h.members
        ],
        "created_at": h.created_at.isoformat(),
    }
