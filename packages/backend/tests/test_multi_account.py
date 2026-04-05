"""Tests for multi-account dashboard (issue #132)."""
def _app():
    from app import create_app
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

def test_create_and_overview():
    app = _app()
    with app.app_context():
        from app.extensions import db
        from app.services.multi_account import FinancialAccount
        db.create_all()
        from app.services.multi_account import create_account, get_overview
        create_account(1, "Chase Checking", "checking", balance=2000)
        create_account(1, "Savings", "savings", balance=5000)
        create_account(1, "Credit Card", "credit", balance=500)
        ov = get_overview(1)
        assert ov["net_worth"] == 6500.0  # 7000 assets - 500 liabilities
        assert ov["total_assets"] == 7000.0
        assert ov["total_liabilities"] == 500.0
        assert ov["account_count"] == 3

def test_overview_empty():
    app = _app()
    with app.app_context():
        from app.extensions import db
        from app.services.multi_account import FinancialAccount
        db.create_all()
        from app.services.multi_account import get_overview
        ov = get_overview(999)
        assert ov["net_worth"] == 0
        assert ov["accounts"] == []

def test_update_balance():
    app = _app()
    with app.app_context():
        from app.extensions import db
        from app.services.multi_account import FinancialAccount
        db.create_all()
        from app.services.multi_account import create_account, update_balance
        a = create_account(1, "Main", balance=100)
        updated = update_balance(a.id, 999.99)
        assert float(updated.balance) == 999.99

def test_invalid_account_type():
    app = _app()
    with app.app_context():
        from app.extensions import db
        from app.services.multi_account import FinancialAccount
        db.create_all()
        from app.services.multi_account import create_account
        import pytest
        with pytest.raises(ValueError):
            create_account(1, "Bad", account_type="invalid_type")
