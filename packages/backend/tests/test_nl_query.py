"""Tests for natural language query (issue #74)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_spend_query():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.nl_query import query
        result = query(1, "How much did I spend this month?")
        assert "answer" in result
        assert "$" in result["answer"]

def test_income_query():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.nl_query import query
        result = query(1, "What was my income last month?")
        assert "income" in result["answer"].lower() or "$" in result["answer"]

def test_count_query():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.nl_query import query
        result = query(1, "How many transactions did I make this month?")
        assert "transactions" in result["answer"]

def test_unknown_query():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.nl_query import query
        result = query(1, "xkcd random gibberish")
        assert result["value"] is None
