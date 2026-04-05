"""Tests for transaction deduplication (issue #113)."""

def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def _add_expense(db, user_id, amount, spent_at):
    from app.models import Expense
    from datetime import date
    e = Expense(user_id=user_id, amount=amount,
                spent_at=date.fromisoformat(spent_at) if isinstance(spent_at,str) else spent_at)
    db.session.add(e); db.session.commit(); return e

def test_exact_duplicate_detected():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        _add_expense(db, 1, 100, "2026-04-01")
        from app.services.dedup import is_duplicate
        from datetime import date
        result = is_duplicate(1, 100, date(2026,4,1))
        assert result["duplicate"] is True
        assert result["confidence"] == "high"

def test_no_duplicate_different_amount():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        _add_expense(db, 1, 100, "2026-04-01")
        from app.services.dedup import is_duplicate
        from datetime import date
        result = is_duplicate(1, 200, date(2026,4,1))
        assert result["duplicate"] is False

def test_find_all_duplicates():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        _add_expense(db, 2, 50, "2026-04-01")
        _add_expense(db, 2, 50, "2026-04-02")
        from app.services.dedup import find_all_duplicates
        pairs = find_all_duplicates(2)
        assert len(pairs) == 1
        assert pairs[0]["amount"] == 50.0

def test_no_duplicates_empty():
    app = _app()
    with app.app_context():
        from app.extensions import db; db.create_all()
        from app.services.dedup import find_all_duplicates
        assert find_all_duplicates(999) == []
