"""Household budgeting service.

Allows multiple users to collaborate on shared household finances
with invite-based membership and aggregated spending views.
"""

from datetime import date, datetime

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense


class Household(db.Model):
    __tablename__ = "households"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    members = db.relationship("HouseholdMember", backref="household", lazy=True)


class HouseholdMember(db.Model):
    __tablename__ = "household_members"
    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("households.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(20), default="member", nullable=False)  # owner/member
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("household_id", "user_id", name="uq_household_user"),
    )


class HouseholdInvite(db.Model):
    __tablename__ = "household_invites"
    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.Integer, db.ForeignKey("households.id"), nullable=False)
    invite_code = db.Column(db.String(64), unique=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    used_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)


def create_household(owner_id: int, name: str) -> dict:
    h = Household(name=name, owner_id=owner_id)
    db.session.add(h)
    db.session.flush()
    m = HouseholdMember(household_id=h.id, user_id=owner_id, role="owner")
    db.session.add(m)
    db.session.commit()
    return {"id": h.id, "name": h.name, "owner_id": owner_id}


def generate_invite(household_id: int, created_by: int, hours: int = 48) -> dict:
    import secrets
    from datetime import timedelta

    code = secrets.token_urlsafe(16)
    expires = datetime.utcnow() + timedelta(hours=hours)
    inv = HouseholdInvite(
        household_id=household_id,
        invite_code=code,
        created_by=created_by,
        expires_at=expires,
    )
    db.session.add(inv)
    db.session.commit()
    return {"invite_code": code, "expires_at": expires.isoformat()}


def accept_invite(user_id: int, invite_code: str) -> dict:
    inv = HouseholdInvite.query.filter_by(invite_code=invite_code, used_by=None).first()
    if not inv:
        raise ValueError("Invalid or expired invite code.")
    if inv.expires_at < datetime.utcnow():
        raise ValueError("Invite code has expired.")

    existing = HouseholdMember.query.filter_by(
        household_id=inv.household_id, user_id=user_id
    ).first()
    if existing:
        raise ValueError("Already a member of this household.")

    m = HouseholdMember(household_id=inv.household_id, user_id=user_id, role="member")
    inv.used_by = user_id
    db.session.add(m)
    db.session.commit()
    return {"household_id": inv.household_id, "role": "member"}


def get_household_members(household_id: int) -> list[dict]:
    members = HouseholdMember.query.filter_by(household_id=household_id).all()
    return [
        {"user_id": m.user_id, "role": m.role, "joined_at": m.joined_at.isoformat()}
        for m in members
    ]


def household_summary(household_id: int, ym: str | None = None) -> dict:
    """Aggregate spending across all household members for a given month."""
    if ym is None:
        ym = date.today().strftime("%Y-%m")
    year, month = map(int, ym.split("-"))

    member_ids = [
        m.user_id
        for m in HouseholdMember.query.filter_by(household_id=household_id).all()
    ]
    if not member_ids:
        return {"month": ym, "total_spending": 0, "total_income": 0, "members": []}

    income = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id.in_(member_ids),
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
        or 0
    )
    spending = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id.in_(member_ids),
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
        or 0
    )

    # Per-member breakdown
    per_member = []
    for uid in member_ids:
        member_spend = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == year,
                extract("month", Expense.spent_at) == month,
                Expense.expense_type != "INCOME",
            )
            .scalar()
            or 0
        )
        per_member.append({"user_id": uid, "spending": round(member_spend, 2)})

    return {
        "month": ym,
        "total_income": round(income, 2),
        "total_spending": round(spending, 2),
        "net_flow": round(income - spending, 2),
        "member_count": len(member_ids),
        "members": per_member,
    }


def get_user_households(user_id: int) -> list[dict]:
    memberships = HouseholdMember.query.filter_by(user_id=user_id).all()
    result = []
    for m in memberships:
        h = Household.query.get(m.household_id)
        if h:
            result.append({
                "id": h.id,
                "name": h.name,
                "role": m.role,
                "member_count": HouseholdMember.query.filter_by(household_id=h.id).count(),
            })
    return result
