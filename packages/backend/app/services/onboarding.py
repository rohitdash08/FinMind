"""Smart onboarding financial setup wizard (issue #101)."""
import logging
from ..extensions import db
from ..models import User, Category, Budget

logger = logging.getLogger("finmind.onboarding")

DEFAULT_CATEGORIES = [
    ("Housing","🏠"),("Groceries","🛒"),("Transport","🚗"),("Dining","🍽️"),
    ("Utilities","💡"),("Healthcare","🏥"),("Entertainment","🎬"),("Shopping","🛍️"),
    ("Fitness","💪"),("Education","📚"),("Insurance","🛡️"),("Savings","💰"),
]
BUDGET_PRESETS = {
    "tight":       {"Housing":1200,"Groceries":300,"Transport":150,"Dining":100,"Utilities":150,"Entertainment":50,"Shopping":100},
    "moderate":    {"Housing":1800,"Groceries":500,"Transport":300,"Dining":250,"Utilities":200,"Entertainment":150,"Shopping":200},
    "comfortable": {"Housing":2500,"Groceries":700,"Transport":500,"Dining":400,"Utilities":250,"Entertainment":300,"Shopping":400},
}

def get_onboarding_status(user_id: int) -> dict:
    cats = db.session.query(Category).filter_by(user_id=user_id).count()
    budgets = db.session.query(Budget).filter_by(user_id=user_id).count()
    user = db.session.get(User, user_id)
    steps = {"profile_complete": bool(user and getattr(user,"name",None)),
             "categories_set": cats >= 3, "budgets_set": budgets >= 1,
             "first_expense": False, "income_recorded": False}
    completed = sum(1 for v in steps.values() if v)
    return {"steps": steps, "completed": completed, "total": len(steps),
            "pct": round(completed/len(steps)*100),
            "next_step": next((k for k,v in steps.items() if not v), None),
            "complete": completed == len(steps)}

def setup_default_categories(user_id: int) -> list:
    existing = {c.name for c in db.session.query(Category).filter_by(user_id=user_id).all()}
    created = []
    for name, icon in DEFAULT_CATEGORIES:
        if name not in existing:
            db.session.add(Category(user_id=user_id, name=name, icon=icon))
            created.append(name)
    db.session.commit()
    return created

def apply_budget_preset(user_id: int, preset: str) -> dict:
    if preset not in BUDGET_PRESETS:
        raise ValueError(f"Unknown preset: {preset}")
    cats = {c.name: c for c in db.session.query(Category).filter_by(user_id=user_id).all()}
    applied = []
    for cat_name, amount in BUDGET_PRESETS[preset].items():
        cat = cats.get(cat_name)
        if cat:
            ex = db.session.query(Budget).filter_by(user_id=user_id, category_id=cat.id).first()
            if ex: ex.limit_amount = amount
            else: db.session.add(Budget(user_id=user_id, category_id=cat.id, limit_amount=amount))
            applied.append({"category": cat_name, "limit": amount})
    db.session.commit()
    return {"preset": preset, "applied": applied, "count": len(applied)}
