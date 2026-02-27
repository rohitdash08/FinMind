"""Smart onboarding financial setup wizard.

Guides new users through initial setup: profile, categories,
budget, accounts, and first expense.
"""

from datetime import datetime
from ..extensions import db


class OnboardingProgress(db.Model):
    __tablename__ = "onboarding_progress"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    current_step = db.Column(db.Integer, default=1)
    completed = db.Column(db.Boolean, default=False)
    skipped_steps = db.Column(db.Text, default="")  # comma-separated step numbers
    profile_data = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)


ONBOARDING_STEPS = [
    {"step": 1, "name": "welcome", "title": "Welcome", "description": "Welcome to FinMind!", "skippable": False},
    {"step": 2, "name": "profile", "title": "Your Profile", "description": "Set your currency and locale", "skippable": False},
    {"step": 3, "name": "categories", "title": "Spending Categories", "description": "Choose or customize your categories", "skippable": True},
    {"step": 4, "name": "budget", "title": "Monthly Budget", "description": "Set your first monthly budget", "skippable": True},
    {"step": 5, "name": "accounts", "title": "Accounts", "description": "Add your bank accounts or wallets", "skippable": True},
    {"step": 6, "name": "first_expense", "title": "First Expense", "description": "Log your first expense", "skippable": True},
    {"step": 7, "name": "complete", "title": "All Set!", "description": "You're ready to go", "skippable": False},
]

DEFAULT_CATEGORIES = [
    "Food & Dining", "Transportation", "Shopping", "Entertainment",
    "Bills & Utilities", "Health", "Education", "Travel", "Other",
]


def get_progress(user_id: int) -> dict:
    p = OnboardingProgress.query.filter_by(user_id=user_id).first()
    if not p:
        p = OnboardingProgress(user_id=user_id)
        db.session.add(p)
        db.session.commit()
    return _serialize(p)


def advance(user_id: int, step_data: dict | None = None) -> dict:
    p = OnboardingProgress.query.filter_by(user_id=user_id).first()
    if not p:
        p = OnboardingProgress(user_id=user_id)
        db.session.add(p)
        db.session.flush()

    if p.completed:
        return _serialize(p)

    if step_data:
        import json
        existing = json.loads(p.profile_data or "{}")
        existing[f"step_{p.current_step}"] = step_data
        p.profile_data = json.dumps(existing)

    if p.current_step < len(ONBOARDING_STEPS):
        p.current_step += 1
    
    if p.current_step >= len(ONBOARDING_STEPS):
        p.completed = True
        p.completed_at = datetime.utcnow()

    db.session.commit()
    return _serialize(p)


def skip_step(user_id: int) -> dict:
    p = OnboardingProgress.query.filter_by(user_id=user_id).first()
    if not p:
        raise ValueError("Onboarding not started")

    current = ONBOARDING_STEPS[p.current_step - 1] if p.current_step <= len(ONBOARDING_STEPS) else None
    if not current or not current["skippable"]:
        raise ValueError("This step cannot be skipped")

    skipped = p.skipped_steps.split(",") if p.skipped_steps else []
    skipped.append(str(p.current_step))
    p.skipped_steps = ",".join(skipped)

    if p.current_step < len(ONBOARDING_STEPS):
        p.current_step += 1

    if p.current_step >= len(ONBOARDING_STEPS):
        p.completed = True
        p.completed_at = datetime.utcnow()

    db.session.commit()
    return _serialize(p)


def reset(user_id: int) -> dict:
    p = OnboardingProgress.query.filter_by(user_id=user_id).first()
    if not p:
        raise ValueError("Onboarding not started")
    p.current_step = 1
    p.completed = False
    p.completed_at = None
    p.skipped_steps = ""
    p.profile_data = "{}"
    db.session.commit()
    return _serialize(p)


def get_suggestions(step: int) -> dict:
    if step == 3:
        return {"categories": DEFAULT_CATEGORIES}
    elif step == 4:
        return {"suggested_budgets": [
            {"category": "Food & Dining", "amount": 500},
            {"category": "Transportation", "amount": 200},
            {"category": "Shopping", "amount": 300},
            {"category": "Entertainment", "amount": 150},
            {"category": "Bills & Utilities", "amount": 400},
        ]}
    return {}


def _serialize(p: OnboardingProgress) -> dict:
    skipped = [int(s) for s in p.skipped_steps.split(",") if s]
    return {
        "id": p.id,
        "current_step": p.current_step,
        "total_steps": len(ONBOARDING_STEPS),
        "completed": p.completed,
        "skipped_steps": skipped,
        "steps": ONBOARDING_STEPS,
        "progress_pct": round((p.current_step - 1) / len(ONBOARDING_STEPS) * 100, 1),
    }
