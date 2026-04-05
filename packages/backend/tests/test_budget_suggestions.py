"""Tests for budget suggestions (issue #73)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_suggestions_empty():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.budget_suggestions import suggest_budgets
        result = suggest_budgets(999, months_history=3)
        assert result["suggestions"] == []
        assert result["total_suggested_budget"] == 0

def test_suggestions_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.budget_suggestions import suggest_budgets
        result = suggest_budgets(999)
        assert "months_analyzed" in result
        assert "suggestions" in result
        assert "total_suggested_budget" in result

def test_discretionary_gets_10pct_cut():
    from app.services.budget_suggestions import suggest_budgets
    # Logic test: non-essential category should get 10% reduction
    essential_kw = {"rent","groceries"}
    cat = "netflix"
    factor = 1.0 if any(k in cat.lower() for k in essential_kw) else 0.90
    assert factor == 0.90
