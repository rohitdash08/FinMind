"""Tests for financial accounts."""
from app.extensions import db
from app.models import FinancialAccount, User


def _create_user(app_fixture):
    with app_fixture.app_context():
        user = User(email="acc@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()
        return user.id


def test_create_account(app_fixture):
    uid = _create_user(app_fixture)
    with app_fixture.app_context():
        a = FinancialAccount(user_id=uid, name="Test Checking", balance=1000)
        db.session.add(a)
        db.session.commit()
        assert a.id is not None
        assert a.account_type == "checking"
        assert float(a.balance) == 1000.0


def test_list_accounts(app_fixture):
    uid = _create_user(app_fixture)
    with app_fixture.app_context():
        db.session.add(FinancialAccount(user_id=uid, name="A1", balance=500))
        db.session.add(FinancialAccount(user_id=uid, name="A2", balance=300, account_type="savings"))
        db.session.commit()
        accounts = FinancialAccount.query.filter_by(user_id=uid, active=True).all()
        assert len(accounts) == 2


def test_consolidated_view(app_fixture):
    uid = _create_user(app_fixture)
    with app_fixture.app_context():
        db.session.add(FinancialAccount(user_id=uid, name="Checking", balance=2000))
        db.session.add(FinancialAccount(user_id=uid, name="Savings", balance=5000, account_type="savings"))
        db.session.add(FinancialAccount(user_id=uid, name="Credit", balance=-500, account_type="credit"))
        db.session.commit()
        accounts = FinancialAccount.query.filter_by(user_id=uid, active=True).all()
        total = sum(float(a.balance) for a in accounts)
        assert total == 6500.0
