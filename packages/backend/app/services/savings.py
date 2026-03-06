from datetime import datetime
from ..extensions import db
from ..models import SavingsGoal, SavingsDeposit


def create_goal(user_id, name, target_amount, deadline=None):
    goal = SavingsGoal(
        user_id=user_id,
        name=name,
        target_amount=target_amount,
        deadline=deadline,
    )
    db.session.add(goal)
    db.session.commit()
    return goal


def get_goals(user_id):
    return (
        db.session.query(SavingsGoal)
        .filter_by(user_id=user_id)
        .order_by(SavingsGoal.created_at.desc())
        .all()
    )


def get_goal(goal_id, user_id):
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id:
        return None
    return goal


def update_goal(goal, name=None, target_amount=None, deadline=None):
    if name is not None:
        goal.name = name
    if target_amount is not None:
        goal.target_amount = target_amount
    if deadline is not None:
        goal.deadline = deadline
    db.session.commit()
    return goal


def delete_goal(goal):
    db.session.delete(goal)
    db.session.commit()


def deposit(goal, amount, note=None):
    d = SavingsDeposit(goal_id=goal.id, amount=amount, note=note)
    db.session.add(d)
    goal.current_amount = (goal.current_amount or 0) + amount
    if goal.current_amount >= goal.target_amount and not goal.completed:
        goal.completed = True
        goal.completed_at = datetime.utcnow()
    db.session.commit()
    return d


def withdraw(goal, amount):
    goal.current_amount = max((goal.current_amount or 0) - amount, 0)
    if goal.current_amount < goal.target_amount:
        goal.completed = False
        goal.completed_at = None
    d = SavingsDeposit(goal_id=goal.id, amount=-amount, note="withdrawal")
    db.session.add(d)
    db.session.commit()
    return d


def get_deposits(goal_id):
    return (
        db.session.query(SavingsDeposit)
        .filter_by(goal_id=goal_id)
        .order_by(SavingsDeposit.deposited_at.desc())
        .all()
    )


def get_milestones(goal):
    pct = (goal.current_amount or 0) / goal.target_amount * 100 if goal.target_amount else 0
    milestones = []
    for threshold in [25, 50, 75, 100]:
        milestones.append({
            "percent": threshold,
            "reached": pct >= threshold,
        })
    return milestones
