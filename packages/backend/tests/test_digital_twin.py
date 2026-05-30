from app.services.digital_twin import (
    create_twin, get_twin, update_twin, list_twins, delete_twin,
    run_simulation, list_simulations, get_simulation,
    add_goal, list_goals, delete_goal,
)


def _create_test_user(app):
    from app.extensions import db
    from app.models import User
    user = User(email="twin_test@example.com", password_hash="hash", preferred_currency="INR")
    db.session.add(user)
    db.session.commit()
    return user.id


def test_create_and_get_twin(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        result = create_twin(uid, {"name": "My Twin", "monthly_income": 5000, "monthly_expenses": 3000})
        assert result["name"] == "My Twin"
        assert result["monthly_income"] == 5000
        assert result["id"] is not None

        fetched = get_twin(uid, result["id"])
        assert fetched is not None
        assert fetched["name"] == "My Twin"


def test_update_twin(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        twin = create_twin(uid, {"name": "Original", "monthly_income": 3000})
        updated = update_twin(uid, twin["id"], {"name": "Updated", "monthly_income": 6000})
        assert updated["name"] == "Updated"
        assert updated["monthly_income"] == 6000


def test_list_twins(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        create_twin(uid, {"name": "Twin A"})
        create_twin(uid, {"name": "Twin B"})
        twins = list_twins(uid)
        assert len(twins) >= 2


def test_delete_twin(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        twin = create_twin(uid, {"name": "Delete Me"})
        assert delete_twin(uid, twin["id"]) is True
        assert get_twin(uid, twin["id"]) is None


def test_run_monte_carlo_simulation(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        twin = create_twin(uid, {
            "name": "Sim Twin",
            "monthly_income": 5000,
            "monthly_expenses": 3000,
            "current_savings": 10000,
            "risk_tolerance": "moderate",
            "retirement_age": 65,
        })
        result = run_simulation(
            uid, twin["id"],
            scenario_name="baseline",
            projection_years=10,
            num_simulations=100,
        )
        assert "final_stats" in result
        assert result["scenario"] == "baseline"
        assert result["final_stats"]["median"] > 0
        assert result["final_stats"]["p10"] > 0
        assert result["final_stats"]["p90"] > 0
        assert "milestone_stats" in result


def test_run_simulation_with_adjustments(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        twin = create_twin(uid, {
            "name": "Adj Twin",
            "monthly_income": 5000,
            "monthly_expenses": 3000,
            "current_savings": 50000,
        })
        result = run_simulation(
            uid, twin["id"],
            scenario_name="what-if-raise",
            projection_years=5,
            num_simulations=50,
            adjustments={"monthly_income": 8000},
        )
        assert result["adjustments"]["monthly_income"] == 8000


def test_list_simulations(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        twin = create_twin(uid, {"name": "List Twin", "monthly_income": 5000, "monthly_expenses": 3000})
        run_simulation(uid, twin["id"], scenario_name="run1", projection_years=5, num_simulations=50)
        run_simulation(uid, twin["id"], scenario_name="run2", projection_years=10, num_simulations=50)
        sims = list_simulations(uid, twin["id"])
        assert len(sims) >= 2


def test_get_simulation(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        twin = create_twin(uid, {"name": "Get Twin", "monthly_income": 5000, "monthly_expenses": 3000})
        run_simulation(uid, twin["id"], scenario_name="test", projection_years=3, num_simulations=50)
        sims = list_simulations(uid, twin["id"])
        result = get_simulation(uid, sims[0]["id"])
        assert result is not None
        assert result["scenario"] == "test"


def test_add_list_goal(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        twin = create_twin(uid, {"name": "Goal Twin", "monthly_income": 5000, "monthly_expenses": 3000})
        goal = add_goal(uid, twin["id"], {
            "name": "Retirement Fund",
            "target_amount": 1000000,
            "target_date": "2050-01-01",
            "priority": "high",
        })
        assert goal["name"] == "Retirement Fund"
        assert goal["target_amount"] == 1000000

        goals = list_goals(uid, twin["id"])
        assert len(goals) == 1
        assert goals[0]["name"] == "Retirement Fund"


def test_delete_goal(app_fixture):
    with app_fixture.app_context():
        uid = _create_test_user(app_fixture)
        twin = create_twin(uid, {"name": "Del Goal", "monthly_income": 5000, "monthly_expenses": 3000})
        goal = add_goal(uid, twin["id"], {
            "name": "Delete Me", "target_amount": 10000, "target_date": "2030-01-01",
        })
        assert delete_goal(uid, goal["id"]) is True
        assert len(list_goals(uid, twin["id"])) == 0
