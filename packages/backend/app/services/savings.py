
from datetime import datetime
from ..extensions import db

class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    currency = db.Column(db.String(10), default="INR", nullable=False)
    deadline = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    milestones = db.relationship("SavingsMilestone", backref="goal", lazy="dynamic")
    deposits = db.relationship("SavingsDeposit", backref="goal", lazy="dynamic")

    @property
    def progress_percent(self):
        return min(100, float(self.current_amount / self.target_amount * 100)) if self.target_amount else 0

class SavingsMilestone(db.Model):
    __tablename__ = "savings_milestones"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    reached = db.Column(db.Boolean, default=False, nullable=False)
    reached_at = db.Column(db.DateTime, nullable=True)

class SavingsDeposit(db.Model):
    __tablename__ = "savings_deposits"
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goals.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

def create_goal(user_id, name, target_amount, **kwargs):
    goal = SavingsGoal(user_id=user_id, name=name, target_amount=target_amount, **kwargs)
    db.session.add(goal)
    db.session.flush()
    for pct in [25, 50, 75, 100]:
        db.session.add(SavingsMilestone(goal_id=goal.id, name=f"{pct}% reached", target_amount=target_amount * pct / 100))
    db.session.commit()
    return goal

def deposit(goal_id, user_id, amount, notes=None):
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.user_id != user_id: raise ValueError("Goal not found")
    if goal.status != "active": raise ValueError("Goal is not active")
    d = SavingsDeposit(goal_id=goal_id, user_id=user_id, amount=amount, notes=notes)
    db.session.add(d)
    goal.current_amount = float(goal.current_amount) + float(amount)
    for m in goal.milestones.filter_by(reached=False).all():
        if float(goal.current_amount) >= float(m.target_amount):
            m.reached = True; m.reached_at = datetime.utcnow()
    if float(goal.current_amount) >= float(goal.target_amount):
        goal.status = "completed"; goal.completed_at = datetime.utcnow()
    db.session.commit()
    return {"deposit_id": d.id, "balance": float(goal.current_amount), "progress": goal.progress_percent}
