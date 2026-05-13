from datetime import date

from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models import Account, Expense, User


def _auth_header_without_redis(app_fixture, email="accounts@example.com"):
    with app_fixture.app_context():
        user = User(email=email, password_hash="unused")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    return user.id, {"Authorization": f"Bearer {token}"}


def test_accounts_can_be_created_listed_and_updated(client, app_fixture, monkeypatch):
    monkeypatch.setattr(
        "app.routes.accounts.cache_delete_patterns", lambda *_args: None
    )
    _, auth_header = _auth_header_without_redis(app_fixture)

    r = client.post(
        "/accounts",
        json={
            "name": "Main Checking",
            "account_type": "checking",
            "balance": 1250.75,
            "currency": "USD",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    account = r.get_json()
    assert account["name"] == "Main Checking"
    assert account["balance"] == 1250.75

    r = client.patch(
        f"/accounts/{account['id']}",
        json={"balance": 1500, "account_type": "savings"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["account_type"] == "savings"

    r = client.get("/accounts", headers=auth_header)
    assert r.status_code == 200
    accounts = r.get_json()
    assert len(accounts) == 1
    assert accounts[0]["balance"] == 1500.0


def test_dashboard_includes_multi_account_overview(client, app_fixture, monkeypatch):
    monkeypatch.setattr("app.routes.dashboard.cache_get", lambda *_args: None)
    monkeypatch.setattr(
        "app.routes.dashboard.cache_set", lambda *_args, **_kwargs: None
    )
    uid, auth_header = _auth_header_without_redis(
        app_fixture, email="dashboard-accounts@example.com"
    )
    with app_fixture.app_context():
        checking = Account(
            user_id=uid,
            name="Checking",
            account_type="checking",
            balance=1000,
            currency="USD",
        )
        savings = Account(
            user_id=uid,
            name="Savings",
            account_type="savings",
            balance=2500,
            currency="USD",
        )
        db.session.add_all([checking, savings])
        db.session.flush()
        db.session.add(
            Expense(
                user_id=uid,
                account_id=checking.id,
                amount=100,
                currency="USD",
                expense_type="EXPENSE",
                notes="Groceries",
                spent_at=date.today(),
            )
        )
        db.session.commit()

    r = client.get("/dashboard/summary", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["summary"]["account_count"] == 2
    assert payload["summary"]["total_account_balance"] == 3500.0
    assert [account["name"] for account in payload["accounts"]] == [
        "Checking",
        "Savings",
    ]
