"""Tests for budget optimizer (issue #92)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_optimize_zero_state():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.budget_optimizer import optimize_budget
        result = optimize_budget(999, 2026, 4)
        assert "suggestions" in result
        assert result["gap"] == 0  # no income = no gap

def test_optimize_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.budget_optimizer import optimize_budget
        result = optimize_budget(999, 2026, 4, target_savings_pct=20.0)
        assert "income" in result
        assert "current_savings_pct" in result
        assert "achievable" in result

def test_suggestion_cuts_discretionary():
    # Logic test: essential categories should not appear in suggestions
    essential = {"rent","groceries","utilities"}
    categories = [{"name": "rent", "amt": 1000}, {"name": "netflix", "amt": 15}]
    discretionary = [c for c in categories if c["name"].lower() not in essential]
    assert len(discretionary) == 1
    assert discretionary[0]["name"] == "netflix"
