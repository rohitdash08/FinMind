from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


USER_ID = 1


# ---------------------------------------------------------------------------
# Savings Goal tests
# ---------------------------------------------------------------------------

def test_create_goal(client):
    resp = client.post(
        "/savings/goals",
        params={"user_id": USER_ID},
        json={"name": "Vacation", "target_amount": "1000.00", "currency": "USD"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Vacation"
    assert Decimal(data["target_amount"]) == Decimal("1000.00")
    assert data["status"] == "active"
    assert data["milestones"] == []


def test_list_goals(client):
    client.post(
        "/savings/goals",
        params={"user_id": USER_ID},
        json={"name": "Car", "target_amount": "5000.00"},
    )
    resp = client.get("/savings/goals", params={"user_id": USER_ID})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_goal(client):
    create_resp = client.post(
        "/savings/goals",
        params={"user_id": USER_ID},
        json={"name": "Emergency Fund", "target_amount": "3000.00"},
    )
    goal_id = create_resp.json()["id"]
    resp = client.get(f"/savings/goals/{goal_id}", params={"user_id": USER_ID})
    assert resp.status_code == 200
    assert resp.json()["id"] == goal_id


def test_get_goal_not_found(client):
    resp = client.get("/savings/goals/999", params={"user_id": USER_ID})
    assert resp.status_code == 404


def test_update_goal(client):
    create_resp = client.post(
        "/savings/goals",
        params={"user_id": USER_ID},
        json={"name": "House", "target_amount": "50000.00"},
    )
    goal_id = create_resp.json()["id"]
    resp = client.patch(
        f"/savings/goals/{goal_id}",
        params={"user_id": USER_ID},
        json={"current_amount": "2000.00", "status": "active"},
    )
    assert resp.status_code == 200
    assert Decimal(resp.json()["current_amount"]) == Decimal("2000.00")


def test_delete_goal(client):
    create_resp = client.post(
        "/savings/goals",
        params={"user_id": USER_ID},
        json={"name": "Laptop", "target_amount": "1500.00"},
    )
    goal_id = create_resp.json()["id"]
    resp = client.delete(f"/savings/goals/{goal_id}", params={"user_id": USER_ID})
    assert resp.status_code == 204
    assert client.get(f"/savings/goals/{goal_id}", params={"user_id": USER_ID}).status_code == 404


# ---------------------------------------------------------------------------
# Milestone tests
# ---------------------------------------------------------------------------

def _create_goal(client):
    resp = client.post(
        "/savings/goals",
        params={"user_id": USER_ID},
        json={"name": "Retirement", "target_amount": "100000.00"},
    )
    return resp.json()["id"]


def test_create_milestone(client):
    goal_id = _create_goal(client)
    resp = client.post(
        f"/savings/goals/{goal_id}/milestones",
        params={"user_id": USER_ID},
        json={"name": "25% reached", "target_amount": "25000.00"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "25% reached"
    assert data["goal_id"] == goal_id
    assert data["reached_at"] is None


def test_list_milestones(client):
    goal_id = _create_goal(client)
    client.post(
        f"/savings/goals/{goal_id}/milestones",
        params={"user_id": USER_ID},
        json={"name": "10% reached", "target_amount": "10000.00"},
    )
    resp = client.get(f"/savings/goals/{goal_id}/milestones", params={"user_id": USER_ID})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_update_milestone(client):
    goal_id = _create_goal(client)
    m_resp = client.post(
        f"/savings/goals/{goal_id}/milestones",
        params={"user_id": USER_ID},
        json={"name": "50% reached", "target_amount": "50000.00"},
    )
    milestone_id = m_resp.json()["id"]
    reached = "2024-06-01T00:00:00"
    resp = client.patch(
        f"/savings/goals/{goal_id}/milestones/{milestone_id}",
        params={"user_id": USER_ID},
        json={"reached_at": reached},
    )
    assert resp.status_code == 200
    assert resp.json()["reached_at"] is not None


def test_delete_milestone(client):
    goal_id = _create_goal(client)
    m_resp = client.post(
        f"/savings/goals/{goal_id}/milestones",
        params={"user_id": USER_ID},
        json={"name": "First milestone", "target_amount": "1000.00"},
    )
    milestone_id = m_resp.json()["id"]
    resp = client.delete(
        f"/savings/goals/{goal_id}/milestones/{milestone_id}",
        params={"user_id": USER_ID},
    )
    assert resp.status_code == 204
