from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ..extensions import db
from ..models import SharedBudget, BudgetMember, SharedExpense, User


def create_budget(user_id, name, description, monthly_limit):
    budget = SharedBudget(
        name=name,
        description=description,
        monthly_limit=monthly_limit,
        created_by=user_id,
    )
    db.session.add(budget)
    db.session.flush()
    owner = BudgetMember(budget_id=budget.id, user_id=user_id, role="owner")
    db.session.add(owner)
    db.session.commit()
    return budget


def add_member(budget_id, owner_id, member_email):
    budget = db.session.get(SharedBudget, budget_id)
    if not budget:
        return None, "budget not found"
    owner_member = budget.members.filter_by(user_id=owner_id, role="owner").first()
    if not owner_member:
        return None, "only the owner can add members"
    user = db.session.query(User).filter_by(email=member_email).first()
    if not user:
        return None, "user not found"
    existing = budget.members.filter_by(user_id=user.id).first()
    if existing:
        return None, "user is already a member"
    member = BudgetMember(budget_id=budget_id, user_id=user.id, role="member")
    db.session.add(member)
    db.session.commit()
    return member, None


def remove_member(budget_id, owner_id, member_id):
    budget = db.session.get(SharedBudget, budget_id)
    if not budget:
        return "budget not found"
    owner_member = budget.members.filter_by(user_id=owner_id, role="owner").first()
    if not owner_member:
        return "only the owner can remove members"
    member = db.session.get(BudgetMember, member_id)
    if not member or member.budget_id != budget_id:
        return "member not found"
    if member.role == "owner":
        return "cannot remove the owner"
    db.session.delete(member)
    db.session.commit()
    return None


def get_budget_summary(budget_id, user_id):
    budget = db.session.get(SharedBudget, budget_id)
    if not budget:
        return None
    is_member = budget.members.filter_by(user_id=user_id).first()
    if not is_member:
        return None
    now = date.today()
    month_start = now.replace(day=1)
    expenses = (
        db.session.query(SharedExpense)
        .filter(
            SharedExpense.budget_id == budget_id,
            SharedExpense.spent_at >= month_start,
        )
        .all()
    )
    total_spent = float(sum(float(e.amount) for e in expenses))
    member_breakdown = {}
    for e in expenses:
        member_breakdown[e.user_id] = member_breakdown.get(e.user_id, 0) + float(e.amount)
    members = budget.members.all()
    return {
        "id": budget.id,
        "name": budget.name,
        "description": budget.description,
        "monthly_limit": budget.monthly_limit,
        "total_spent": total_spent,
        "remaining": budget.monthly_limit - total_spent,
        "created_by": budget.created_by,
        "members": [
            {"id": m.id, "user_id": m.user_id, "role": m.role}
            for m in members
        ],
        "member_breakdown": member_breakdown,
    }


def get_user_budgets(user_id):
    memberships = (
        db.session.query(BudgetMember)
        .filter_by(user_id=user_id)
        .all()
    )
    budget_ids = [m.budget_id for m in memberships]
    if not budget_ids:
        return []
    budgets = (
        db.session.query(SharedBudget)
        .filter(SharedBudget.id.in_(budget_ids))
        .all()
    )
    return [
        {
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "monthly_limit": b.monthly_limit,
            "created_by": b.created_by,
        }
        for b in budgets
    ]


def add_expense(budget_id, user_id, amount, description, spent_at=None):
    budget = db.session.get(SharedBudget, budget_id)
    if not budget:
        return None, "budget not found"
    is_member = budget.members.filter_by(user_id=user_id).first()
    if not is_member:
        return None, "not a member of this budget"
    try:
        parsed_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None, "invalid amount"
    expense = SharedExpense(
        budget_id=budget_id,
        user_id=user_id,
        amount=parsed_amount,
        description=description,
        spent_at=date.fromisoformat(spent_at) if spent_at else date.today(),
    )
    db.session.add(expense)
    db.session.commit()
    return expense, None


def list_expenses(budget_id, user_id):
    budget = db.session.get(SharedBudget, budget_id)
    if not budget:
        return None
    is_member = budget.members.filter_by(user_id=user_id).first()
    if not is_member:
        return None
    expenses = (
        db.session.query(SharedExpense)
        .filter_by(budget_id=budget_id)
        .order_by(SharedExpense.spent_at.desc())
        .all()
    )
    return [
        {
            "id": e.id,
            "user_id": e.user_id,
            "amount": float(e.amount),
            "description": e.description,
            "date": e.spent_at.isoformat(),
        }
        for e in expenses
    ]
