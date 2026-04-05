"""Tests for savings goals (issue #133)."""
import pytest

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_create_and_list_goal():
    app = _app()
    with app.app_context():
        from app.extensions import db
        from app.services.savings import SavingsGoal, SavingsMilestone
        db.create_all()
        from app.services.savings import create_goal, list_goals
        g = create_goal(1, "Vacation Fund", 1000.0)
        assert g.id is not None
        goals = list_goals(1)
        assert len(goals) == 1
        assert goals[0]["name"] == "Vacation Fund"

def test_milestones_created_on_goal():
    app = _app()
    with app.app_context():
        from app.extensions import db
        from app.services.savings import SavingsGoal, SavingsMilestone
        db.create_all()
        from app.services.savings import create_goal
        from app.extensions import db as _db
        g = create_goal(1, "Car Fund", 5000.0)
        ms = _db.session.query(SavingsMilestone).filter_by(goal_id=g.id).all()
        assert len(ms) == 4
        assert {m.pct for m in ms} == {25, 50, 75, 100}

def test_contribution_reaches_milestone():
    app = _app()
    with app.app_context():
        from app.extensions import db
        from app.services.savings import SavingsGoal, SavingsMilestone
        db.create_all()
        from app.services.savings import create_goal, add_contribution
        g = create_goal(2, "Emergency Fund", 1000.0)
        result = add_contribution(g.id, 250.0)  # exactly 25%
        assert 25 in result["milestones_reached"]

def test_goal_completion():
    app = _app()
    with app.app_context():
        from app.extensions import db
        from app.services.savings import SavingsGoal, SavingsMilestone
        db.create_all()
        from app.services.savings import create_goal, add_contribution, get_goal
        g = create_goal(3, "Laptop", 500.0)
        add_contribution(g.id, 500.0)
        detail = get_goal(g.id)
        assert detail["completed"] is True
        assert detail["progress_pct"] == 100.0
