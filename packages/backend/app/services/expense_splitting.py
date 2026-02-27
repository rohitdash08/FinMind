"""Expense splitting & shared costs.

Split expenses among participants, track who owes whom,
and settle debts with minimal transactions.
"""

from datetime import datetime, date
from collections import defaultdict
from ..extensions import db


class SplitGroup(db.Model):
    __tablename__ = "split_groups"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship("SplitMember", backref="group", cascade="all, delete-orphan", lazy=True)
    expenses = db.relationship("SplitExpense", backref="group", cascade="all, delete-orphan", lazy=True)


class SplitMember(db.Model):
    __tablename__ = "split_members"
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("split_groups.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(300), nullable=True)


class SplitExpense(db.Model):
    __tablename__ = "split_expenses"
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("split_groups.id"), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid_by_id = db.Column(db.Integer, db.ForeignKey("split_members.id"), nullable=False)
    split_type = db.Column(db.String(20), default="equal")  # equal, exact, percentage
    date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    paid_by = db.relationship("SplitMember", foreign_keys=[paid_by_id])
    shares = db.relationship("ExpenseShare", backref="expense", cascade="all, delete-orphan", lazy=True)


class ExpenseShare(db.Model):
    __tablename__ = "expense_shares"
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("split_expenses.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("split_members.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)

    member = db.relationship("SplitMember", foreign_keys=[member_id])


def create_group(user_id: int, name: str, members: list[dict]) -> dict:
    if not name.strip():
        raise ValueError("Group name is required")
    if len(members) < 2:
        raise ValueError("At least 2 members required")

    group = SplitGroup(user_id=user_id, name=name.strip())
    db.session.add(group)
    db.session.flush()

    for m in members:
        db.session.add(SplitMember(group_id=group.id, name=m["name"], email=m.get("email")))

    db.session.commit()
    return _serialize_group(group)


def get_groups(user_id: int) -> list[dict]:
    groups = SplitGroup.query.filter_by(user_id=user_id).order_by(SplitGroup.created_at.desc()).all()
    return [_serialize_group(g) for g in groups]


def get_group(user_id: int, group_id: int) -> dict | None:
    g = SplitGroup.query.filter_by(id=group_id, user_id=user_id).first()
    return _serialize_group(g) if g else None


def delete_group(user_id: int, group_id: int) -> bool:
    g = SplitGroup.query.filter_by(id=group_id, user_id=user_id).first()
    if not g:
        return False
    db.session.delete(g)
    db.session.commit()
    return True


def add_expense(user_id: int, group_id: int, description: str, amount: float,
                paid_by_id: int, split_type: str = "equal", shares: list[dict] | None = None) -> dict:
    g = SplitGroup.query.filter_by(id=group_id, user_id=user_id).first()
    if not g:
        raise ValueError("Group not found")
    if amount <= 0:
        raise ValueError("Amount must be positive")

    exp = SplitExpense(
        group_id=g.id, description=description.strip(), amount=amount,
        paid_by_id=paid_by_id, split_type=split_type,
    )
    db.session.add(exp)
    db.session.flush()

    member_ids = [m.id for m in g.members]

    if split_type == "equal":
        per_person = round(amount / len(member_ids), 2)
        for mid in member_ids:
            db.session.add(ExpenseShare(expense_id=exp.id, member_id=mid, amount=per_person))
    elif split_type == "exact" and shares:
        for s in shares:
            db.session.add(ExpenseShare(expense_id=exp.id, member_id=s["member_id"], amount=float(s["amount"])))
    elif split_type == "percentage" and shares:
        for s in shares:
            share_amt = round(amount * float(s["percentage"]) / 100, 2)
            db.session.add(ExpenseShare(expense_id=exp.id, member_id=s["member_id"], amount=share_amt))
    else:
        # Default equal
        per_person = round(amount / len(member_ids), 2)
        for mid in member_ids:
            db.session.add(ExpenseShare(expense_id=exp.id, member_id=mid, amount=per_person))

    db.session.commit()
    return _serialize_expense(exp)


def get_balances(user_id: int, group_id: int) -> dict:
    """Calculate who owes whom in the group."""
    g = SplitGroup.query.filter_by(id=group_id, user_id=user_id).first()
    if not g:
        raise ValueError("Group not found")

    # Net balance per member: positive = owed money, negative = owes money
    balances = defaultdict(float)
    member_names = {m.id: m.name for m in g.members}

    for exp in g.expenses:
        # Payer gets credit for full amount
        balances[exp.paid_by_id] += exp.amount
        # Each share is a debit
        for share in exp.shares:
            balances[share.member_id] -= share.amount

    result = [
        {"member_id": mid, "name": member_names.get(mid, "Unknown"), "balance": round(bal, 2)}
        for mid, bal in balances.items()
    ]
    result.sort(key=lambda x: x["balance"])

    return {"group_id": group_id, "balances": result}


def calculate_settlements(user_id: int, group_id: int) -> list[dict]:
    """Calculate minimal transactions to settle all debts."""
    bal_data = get_balances(user_id, group_id)
    balances = bal_data["balances"]

    debtors = [(b["member_id"], b["name"], -b["balance"]) for b in balances if b["balance"] < -0.01]
    creditors = [(b["member_id"], b["name"], b["balance"]) for b in balances if b["balance"] > 0.01]

    debtors.sort(key=lambda x: x[2], reverse=True)
    creditors.sort(key=lambda x: x[2], reverse=True)

    settlements = []
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        d_id, d_name, d_amt = debtors[i]
        c_id, c_name, c_amt = creditors[j]
        transfer = min(d_amt, c_amt)

        if transfer > 0.01:
            settlements.append({
                "from_id": d_id, "from_name": d_name,
                "to_id": c_id, "to_name": c_name,
                "amount": round(transfer, 2),
            })

        debtors[i] = (d_id, d_name, d_amt - transfer)
        creditors[j] = (c_id, c_name, c_amt - transfer)

        if debtors[i][2] < 0.01:
            i += 1
        if creditors[j][2] < 0.01:
            j += 1

    return settlements


def _serialize_group(g: SplitGroup) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "members": [{"id": m.id, "name": m.name, "email": m.email} for m in g.members],
        "expense_count": len(g.expenses),
        "total_amount": round(sum(e.amount for e in g.expenses), 2),
        "created_at": g.created_at.isoformat(),
    }


def _serialize_expense(e: SplitExpense) -> dict:
    return {
        "id": e.id,
        "description": e.description,
        "amount": e.amount,
        "paid_by": {"id": e.paid_by.id, "name": e.paid_by.name},
        "split_type": e.split_type,
        "shares": [{"member_id": s.member_id, "name": s.member.name, "amount": s.amount} for s in e.shares],
        "date": e.date.isoformat(),
    }
