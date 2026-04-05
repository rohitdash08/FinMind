"""Tests for advanced search (issue #105)."""
def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def _add_expense(db, user_id, amount, notes, spent_at="2026-04-01"):
    from app.models import Expense
    from datetime import date
    e = Expense(user_id=user_id, amount=amount, notes=notes,
                spent_at=date.fromisoformat(spent_at))
    db.session.add(e); db.session.commit(); return e

def test_search_by_query():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        _add_expense(db, 1, 50, "Starbucks Coffee")
        _add_expense(db, 1, 100, "Amazon Purchase")
        from app.services.search import search
        result = search(1, query="starbucks")
        assert len(result["expenses"]) == 1
        assert "Starbucks" in result["expenses"][0]["notes"]

def test_search_amount_filter():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        _add_expense(db, 2, 10, "cheap"); _add_expense(db, 2, 500, "expensive")
        from app.services.search import search
        result = search(2, amount_min=100)
        assert all(e["amount"] >= 100 for e in result["expenses"])

def test_search_empty():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.search import search
        result = search(999, query="xyzzy")
        assert result["total"] == 0
