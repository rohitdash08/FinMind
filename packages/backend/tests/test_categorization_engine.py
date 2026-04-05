"""Tests for categorization engine (issue #91)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_categorize_transport():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.categorization_engine import categorize
        result = categorize(1, "Uber Trip Downtown")
        assert result["category"] == "Transport"
        assert result["confidence"] in ("high","medium")

def test_categorize_dining():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.categorization_engine import categorize
        assert categorize(1, "Starbucks Coffee")["category"] == "Dining"

def test_categorize_unknown():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.categorization_engine import categorize
        result = categorize(1, "ZXQWERTY RANDOM 9999")
        assert result["category"] is None
        assert result["confidence"] == "none"

def test_categorize_income():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.categorization_engine import categorize
        result = categorize(1, "Direct Deposit Payroll")
        assert result["category"] == "Income"
