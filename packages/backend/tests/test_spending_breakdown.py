from datetime import date


def test_spending_breakdown_classifies_categories(client, auth_header):
    r = client.post("/categories", json={"name": "Groceries"}, headers=auth_header)
    food_id = r.get_json()["id"]

    r = client.post("/categories", json={"name": "Entertainment"}, headers=auth_header)
    ent_id = r.get_json()["id"]

    r = client.post("/expenses", json={
        "amount": 200, "description": "Groceries", "date": date.today().isoformat(),
        "category_id": food_id,
    }, headers=auth_header)
    assert r.status_code == 201

    r = client.post("/expenses", json={
        "amount": 50, "description": "Netflix", "date": date.today().isoformat(),
        "category_id": ent_id,
    }, headers=auth_header)
    assert r.status_code == 201

    r = client.get("/spending/breakdown", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "essential" in data
    assert "discretionary" in data
    assert data["total_spending"] >= 250
    assert data["essential"]["total"] >= 200
    assert data["discretionary"]["total"] >= 50


def test_spending_breakdown_supports_month_filter(client, auth_header):
    r = client.get(f"/spending/breakdown?month={date.today().strftime('%Y-%m')}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["period"] == date.today().strftime("%Y-%m")


def test_update_spending_category(client, auth_header):
    r = client.post("/categories", json={"name": "Transport"}, headers=auth_header)
    cat_id = r.get_json()["id"]

    r = client.patch(f"/spending/categories/{cat_id}", json={"is_essential": False}, headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["message"] == "updated"

    r = client.patch(f"/spending/categories/{cat_id}", json={"is_essential": True}, headers=auth_header)
    assert r.status_code == 200


def test_update_nonexistent_category_returns_404(client, auth_header):
    r = client.patch("/spending/categories/99999", json={"is_essential": True}, headers=auth_header)
    assert r.status_code == 404


def test_spending_trends_endpoint(client, auth_header):
    r = client.get("/spending/trends?months=3", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "trends" in data
    assert len(data["trends"]) <= 3


def test_essential_default_classification(app_fixture):
    from app.extensions import db
    from app.models import Category, Expense, User
    from app.services.spending_breakdown import get_spending_breakdown

    with app_fixture.app_context():
        user = User(email="default@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        cat = Category(user_id=user.id, name="Rent")
        db.session.add(cat)
        db.session.commit()

        exp = Expense(
            user_id=user.id, category_id=cat.id,
            amount=1000, notes="Rent", spent_at=date.today(),
        )
        db.session.add(exp)
        db.session.commit()

        breakdown = get_spending_breakdown(user.id)
        assert breakdown["essential"]["total"] >= 1000
