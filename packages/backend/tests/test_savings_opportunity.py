from datetime import date, timedelta


def test_list_savings_suggestions_endpoint(client, auth_header):
    r = client.get("/savings/suggestions", headers=auth_header)
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_generate_savings_suggestions_endpoint(client, auth_header):
    r = client.post("/savings/suggestions/generate", headers=auth_header)
    assert r.status_code == 200
    suggestions = r.get_json()
    assert isinstance(suggestions, list)


def test_refresh_suggestions_clears_and_regenerates(client, auth_header):
    r = client.post("/savings/suggestions/generate", headers=auth_header)
    assert r.status_code == 200

    r = client.post("/savings/suggestions/refresh", headers=auth_header)
    assert r.status_code == 200
    suggestions = r.get_json()
    assert isinstance(suggestions, list)


def test_dismiss_suggestion(client, auth_header):
    r = client.post("/savings/suggestions/generate", headers=auth_header)
    assert r.status_code == 200
    suggestions = r.get_json()
    if suggestions:
        sid = suggestions[0]["id"]
        r = client.post(f"/savings/suggestions/{sid}/dismiss", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["message"] == "dismissed"

        r = client.get("/savings/suggestions", headers=auth_header)
        remaining = r.get_json()
        assert all(s["id"] != sid for s in remaining)


def test_dismiss_nonexistent_returns_404(client, auth_header):
    r = client.post("/savings/suggestions/99999/dismiss", headers=auth_header)
    assert r.status_code == 404


def test_detect_unused_subscription(app_fixture):
    from app.extensions import db
    from app.models import Expense, RecurringCadence, RecurringExpense, User
    from app.services.savings_opportunity import _detect_unused_subscriptions

    with app_fixture.app_context():
        user = User(email="unused@test.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        rec = RecurringExpense(
            user_id=user.id, amount=15.0, notes="netflix subscription",
            cadence=RecurringCadence.MONTHLY, start_date=date.today() - timedelta(days=365),
        )
        db.session.add(rec)
        db.session.commit()

        results = _detect_unused_subscriptions(user.id)
        assert len(results) >= 1
        assert results[0]["suggestion_type"] == "unused_subscription"
        assert "netflix" in results[0]["title"].lower()
