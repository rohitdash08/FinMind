"""Tests for spending insights (issue #89)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_insights_structure():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.spending_insights import generate_insights
        result = generate_insights(999, 2026, 4)
        assert "insights" in result
        assert "total_this_month" in result
        assert isinstance(result["insights"], list)

def test_insights_zero_state():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.spending_insights import generate_insights
        result = generate_insights(999, 2026, 4)
        assert result["total_this_month"] == 0

def test_insight_types():
    from app.services.spending_insights import generate_insights
    # Just verify valid impact values if insights are produced
    valid_impacts = {"negative","positive","neutral","info"}
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        result = generate_insights(999, 2026, 4)
        for i in result["insights"]:
            assert i["impact"] in valid_impacts
