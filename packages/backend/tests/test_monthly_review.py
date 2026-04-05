"""Tests for guided monthly review (issue #102)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_review_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.monthly_review import generate_monthly_review
        result = generate_monthly_review(999, 2026, 4)
        assert "steps" in result
        assert len(result["steps"]) == 4
        assert result["steps"][0]["step"] == 1

def test_review_zero_state():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.monthly_review import generate_monthly_review
        result = generate_monthly_review(999, 2026, 4)
        summary = result["steps"][0]["data"]
        assert summary["income"] == 0
        assert summary["savings"] == 0

def test_action_items_uncategorized():
    from app.services.monthly_review import generate_monthly_review
    from app import create_app
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        from app.extensions import db
        from app.models import Expense
        from datetime import date
        db.create_all()
        e = Expense(user_id=5, amount=100, spent_at=date(2026,4,1))
        db.session.add(e); db.session.commit()
        result = generate_monthly_review(5, 2026, 4)
        actions = result["steps"][2]["data"]["items"]
        assert any("ategoriz" in a for a in actions)
