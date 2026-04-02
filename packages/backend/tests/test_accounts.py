"""Tests for multi-account CRUD and dashboard overview."""
import pytest
from flask import Flask
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models import User, Account, AccountType, Expense
from app.routes import register_routes


@pytest.fixture
def app():
    """Create test app with in-memory database."""
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY="test-secret-key",
        TESTING=True,
    )
    db.init_app(app)
    jwt.init_app(app) if "jwt" not in app.extensions else None
    
    from flask_jwt_extended import JWTManager
    jwt = JWTManager(app)
    
    register_routes(app)
    
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def test_user(app):
    """Create test user."""
    with app.app_context():
        user = User(
            email="test@example.com",
            password_hash="hashed_password",
            preferred_currency="INR",
        )
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def auth_header(app, test_user):
    """Create JWT auth header."""
    with app.app_context():
        token = create_access_token(identity=str(test_user))
        return {"Authorization": f"Bearer {token}"}


class TestAccountCRUD:
    """Tests for account CRUD operations."""

    def test_list_accounts_empty(self, client, auth_header):
        """Test listing accounts when none exist."""
        response = client.get("/accounts/", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert data["accounts"] == []

    def test_create_account(self, client, auth_header):
        """Test creating a new account."""
        response = client.post(
            "/accounts/",
            headers=auth_header,
            json={
                "name": "Main Checking",
                "account_type": "CHECKING",
                "balance": 1000.50,
                "currency": "INR",
            },
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data["name"] == "Main Checking"
        assert data["account_type"] == "CHECKING"
        assert data["balance"] == 1000.50
        assert data["currency"] == "INR"
        assert data["is_active"] is True

    def test_create_account_invalid_type(self, client, auth_header):
        """Test creating account with invalid type."""
        response = client.post(
            "/accounts/",
            headers=auth_header,
            json={
                "name": "Test Account",
                "account_type": "INVALID_TYPE",
                "balance": 100,
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "Invalid account type" in data["error"]

    def test_create_account_missing_name(self, client, auth_header):
        """Test creating account without name."""
        response = client.post(
            "/accounts/",
            headers=auth_header,
            json={"balance": 100},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "name is required" in data["error"]

    def test_get_account(self, client, auth_header):
        """Test getting a specific account."""
        # Create account first
        create_response = client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "Savings Account", "account_type": "SAVINGS", "balance": 5000},
        )
        account_id = create_response.get_json()["id"]

        # Get the account
        response = client.get(f"/accounts/{account_id}", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Savings Account"
        assert data["account_type"] == "SAVINGS"

    def test_get_account_not_found(self, client, auth_header):
        """Test getting non-existent account."""
        response = client.get("/accounts/999", headers=auth_header)
        assert response.status_code == 404

    def test_update_account(self, client, auth_header):
        """Test updating an account."""
        # Create account
        create_response = client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "Old Name", "balance": 100},
        )
        account_id = create_response.get_json()["id"]

        # Update account
        response = client.put(
            f"/accounts/{account_id}",
            headers=auth_header,
            json={"name": "New Name", "balance": 500},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "New Name"
        assert data["balance"] == 500

    def test_delete_account_soft(self, client, auth_header):
        """Test soft deleting an account."""
        # Create account
        create_response = client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "To Delete", "balance": 100},
        )
        account_id = create_response.get_json()["id"]

        # Soft delete
        response = client.delete(f"/accounts/{account_id}", headers=auth_header)
        assert response.status_code == 200

        # Verify it's inactive
        get_response = client.get(f"/accounts/{account_id}", headers=auth_header)
        assert get_response.get_json()["is_active"] is False

    def test_list_accounts_exclude_inactive(self, client, auth_header):
        """Test that inactive accounts are excluded by default."""
        # Create active account
        client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "Active Account", "balance": 100},
        )

        # Create and deactivate another account
        create_response = client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "Inactive Account", "balance": 200},
        )
        account_id = create_response.get_json()["id"]
        client.delete(f"/accounts/{account_id}", headers=auth_header)

        # List accounts (should only show active)
        response = client.get("/accounts/", headers=auth_header)
        data = response.get_json()
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["name"] == "Active Account"

    def test_list_accounts_include_inactive(self, client, auth_header):
        """Test including inactive accounts in list."""
        # Create and deactivate an account
        create_response = client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "Inactive Account", "balance": 200},
        )
        account_id = create_response.get_json()["id"]
        client.delete(f"/accounts/{account_id}", headers=auth_header)

        # List with include_inactive
        response = client.get("/accounts/?include_inactive=true", headers=auth_header)
        data = response.get_json()
        assert len(data["accounts"]) >= 1


class TestDashboardOverview:
    """Tests for multi-account dashboard overview."""

    def test_overview_no_accounts(self, client, auth_header):
        """Test overview when no accounts exist."""
        response = client.get("/dashboard/overview", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert data["net_worth"]["total_balance"] == 0.0
        assert data["accounts"] == []
        assert data["summary"]["total_accounts"] == 0

    def test_overview_single_account(self, client, auth_header):
        """Test overview with single account."""
        # Create account
        client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "Checking", "account_type": "CHECKING", "balance": 1000},
        )

        response = client.get("/dashboard/overview", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        assert data["net_worth"]["total_balance"] == 1000.0
        assert len(data["accounts"]) == 1
        assert data["summary"]["total_accounts"] == 1

    def test_overview_multiple_accounts(self, client, auth_header):
        """Test overview with multiple accounts."""
        # Create multiple accounts
        client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "Checking", "account_type": "CHECKING", "balance": 2000},
        )
        client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "Savings", "account_type": "SAVINGS", "balance": 5000},
        )
        client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "Credit Card", "account_type": "CREDIT", "balance": -500},
        )

        response = client.get("/dashboard/overview", headers=auth_header)
        assert response.status_code == 200
        data = response.get_json()
        # Net worth = 2000 + 5000 - 500 = 6500
        assert data["net_worth"]["total_balance"] == 6500.0
        assert len(data["accounts"]) == 3
        assert data["summary"]["total_accounts"] == 3

    def test_overview_multi_currency(self, client, auth_header):
        """Test overview with multiple currencies."""
        client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "INR Account", "balance": 1000, "currency": "INR"},
        )
        client.post(
            "/accounts/",
            headers=auth_header,
            json={"name": "USD Account", "balance": 500, "currency": "USD"},
        )

        response = client.get("/dashboard/overview", headers=auth_header)
        data = response.get_json()
        assert "INR" in data["net_worth"]["by_currency"]
        assert "USD" in data["net_worth"]["by_currency"]
        assert data["net_worth"]["by_currency"]["INR"] == 1000.0
        assert data["net_worth"]["by_currency"]["USD"] == 500.0

    def test_overview_unauthorized(self, client):
        """Test overview without authentication."""
        response = client.get("/dashboard/overview")
        assert response.status_code == 401


class TestAccountTypes:
    """Test all account types are valid."""

    def test_all_account_types(self, client, auth_header):
        """Test creating accounts with all valid types."""
        valid_types = ["CHECKING", "SAVINGS", "CREDIT", "INVESTMENT", "CASH", "OTHER"]
        
        for acc_type in valid_types:
            response = client.post(
                "/accounts/",
                headers=auth_header,
                json={"name": f"{acc_type} Account", "account_type": acc_type, "balance": 100},
            )
            assert response.status_code == 201
            data = response.get_json()
            assert data["account_type"] == acc_type