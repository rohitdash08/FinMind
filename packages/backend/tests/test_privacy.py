from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models import AuditLog, Category, Expense, User


def _auth_for_user(client, app_fixture, email="privacy@test.com", password="secret123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    with app_fixture.app_context():
        user = db.session.query(User).filter_by(email=email).one()
        access_token = create_access_token(identity=str(user.id))
    return {
        "Authorization": f"Bearer {access_token}",
        "password": password,
        "email": email,
    }


def test_export_personal_data_package(client, app_fixture):
    auth = _auth_for_user(client, app_fixture)
    headers = {"Authorization": auth["Authorization"]}
    with app_fixture.app_context():
        user = db.session.query(User).filter_by(email=auth["email"]).one()
        category = Category(user_id=user.id, name="Groceries")
        db.session.add(category)
        db.session.flush()
        db.session.add(
            Expense(
                user_id=user.id,
                category_id=category.id,
                amount="12.50",
                currency="USD",
                notes="market",
            )
        )
        db.session.commit()

    r = client.get("/privacy/export", headers=headers)

    assert r.status_code == 200
    data = r.get_json()
    assert data["user"]["email"] == auth["email"]
    assert data["categories"][0]["name"] == "Groceries"
    assert data["expenses"][0]["amount"] == "12.50"
    with app_fixture.app_context():
        assert db.session.query(AuditLog).filter_by(action="PII_EXPORT").count() == 1


def test_delete_personal_data_requires_password(client, app_fixture):
    auth = _auth_for_user(client, app_fixture)
    headers = {"Authorization": auth["Authorization"]}

    r = client.post("/privacy/delete", json={}, headers=headers)
    assert r.status_code == 400

    r = client.post("/privacy/delete", json={"password": "wrong"}, headers=headers)
    assert r.status_code == 403


def test_delete_personal_data_removes_user_owned_records(client, app_fixture):
    auth = _auth_for_user(client, app_fixture)
    headers = {"Authorization": auth["Authorization"]}
    with app_fixture.app_context():
        user = db.session.query(User).filter_by(email=auth["email"]).one()
        db.session.add(Category(user_id=user.id, name="Travel"))
        db.session.commit()

    r = client.post(
        "/privacy/delete", json={"password": auth["password"]}, headers=headers
    )

    assert r.status_code == 200
    with app_fixture.app_context():
        assert db.session.query(User).filter_by(email=auth["email"]).first() is None
        assert db.session.query(Category).count() == 0
        delete_log = db.session.query(AuditLog).filter(
            AuditLog.action.like("PII_DELETE:user:%")
        )
        assert delete_log.count() == 1
        assert delete_log.one().user_id is None
