"""Tests for GDPR PII Export & Delete Workflow."""

import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models import User, Category, Expense, AuditLog


@pytest.fixture
def app():
    """Create test application."""
    with patch("app.config.Config") as mock_cfg:
        mock_cfg.database_url = "sqlite:///:memory:"
        mock_cfg.jwt_secret_key = "test-secret"
        mock_cfg.redis_url = "redis://localhost:6379/0"
        mock_cfg.openaic_api_key = None
        mock_cfg.gemini_api_key = None
        mock_cfg.gemini_model = "gemini-1.5-flash"
        mock_cfg.twilio_account_sid = None
        mock_cfg.twilio_auth_token = None
        mock_cfg.twilio_whatsapp_from = None
        mock_cfg.email_from = "test@example.com"

        app = create_app(mock_cfg)
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True

        with app.app_context():
            db.create_all()
            yield app
            db.drop_all()


@pytest.fixture
def client(app):
    """Test client."""
    return app.test_client()


@pytest.fixture
def auth_headers(app, client):
    """Create a test user and return auth headers."""
    with app.app_context():
        user = User(
            email="test@example.com",
            password_hash="hashed_password",
            preferred_currency="USD",
        )
        db.session.add(user)
        db.session.commit()
        uid = user.id

    # Login to get token
    response = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "password123"
    })
    token = response.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, uid


class TestGDPRExport:
    """Test GDPR data export functionality."""

    def test_export_initiate(self, client, auth_headers):
        """Test initiating a GDPR export."""
        headers, uid = auth_headers

        with patch("app.services.gdpr.redis_client") as mock_redis:
            mock_redis.setex = MagicMock()

            response = client.post("/gdpr/export", headers=headers)
            assert response.status_code == 202
            data = response.get_json()
            assert "download_token" in data
            assert "download_url" in data
            assert data["expires_in_seconds"] == 900

    def test_export_download_invalid_token(self, client):
        """Test downloading with invalid token."""
        response = client.get("/gdpr/export/invalid_token")
        assert response.status_code == 404

    def test_export_requires_auth(self, client):
        """Test that export requires authentication."""
        response = client.post("/gdpr/export")
        assert response.status_code == 401


class TestGDPRDeletion:
    """Test GDPR deletion workflow."""

    def test_deletion_initiate(self, client, auth_headers):
        """Test initiating GDPR deletion."""
        headers, uid = auth_headers

        with patch("app.services.gdpr.redis_client") as mock_redis:
            mock_redis.setex = MagicMock()

            response = client.post("/gdpr/delete", headers=headers)
            assert response.status_code == 202
            data = response.get_json()
            assert "confirmation_token" in data
            assert data["grace_period_days"] == 30

    def test_deletion_confirm_invalid_token(self, client, auth_headers):
        """Test confirming deletion with invalid token."""
        headers, uid = auth_headers

        with patch("app.services.gdpr.redis_client") as mock_redis:
            mock_redis.get = MagicMock(return_value=None)

            response = client.delete("/gdpr/delete/invalid_token", headers=headers)
            assert response.status_code == 404

    def test_deletion_cancel_invalid_token(self, client, auth_headers):
        """Test cancelling deletion with invalid token."""
        headers, uid = auth_headers

        with patch("app.services.gdpr.redis_client") as mock_redis:
            mock_redis.get = MagicMock(return_value=None)

            response = client.post("/gdpr/delete/invalid_token/cancel", headers=headers)
            assert response.status_code == 404

    def test_deletion_requires_auth(self, client):
        """Test that deletion requires authentication."""
        response = client.post("/gdpr/delete")
        assert response.status_code == 401


class TestGDPRServiceUnit:
    """Unit tests for GDPRService."""

    def test_export_user_data_not_found(self, app):
        """Test export raises error for non-existent user."""
        from app.services.gdpr import GDPRService

        with app.app_context():
            with pytest.raises(ValueError):
                GDPRService.export_user_data(99999)

    def test_generate_export_package(self, app):
        """Test export package generation."""
        from app.services.gdpr import GDPRService

        with app.app_context():
            user = User(email="gdpr@test.com", password_hash="hash")
            db.session.add(user)
            db.session.commit()

            with patch("app.services.gdpr.redis_client") as mock_redis:
                mock_redis.setex = MagicMock()
                token, url = GDPRService.generate_export_package(user.id)
                assert token is not None
                assert "/gdpr/download/" in url

    def test_get_deletion_status_not_found(self, app):
        """Test get_deletion_status returns None for invalid token."""
        from app.services.gdpr import GDPRService

        with patch("app.services.gdpr.redis_client") as mock_redis:
            mock_redis.get = MagicMock(return_value=None)
            status = GDPRService.get_deletion_status("invalid_token")
            assert status is None

    def test_cancel_deletion_not_found(self, app):
        """Test cancel_deletion returns False for invalid token."""
        from app.services.gdpr import GDPRService

        with patch("app.services.gdpr.redis_client") as mock_redis:
            mock_redis.get = MagicMock(return_value=None)
            result = GDPRService.cancel_user_deletion("invalid_token")
            assert result is False

    def test_export_to_csv(self, app):
        """Test CSV export conversion."""
        from app.services.gdpr import GDPRService

        export_data = {
            "expenses": [
                {"id": 1, "amount": "100.00", "currency": "USD"},
                {"id": 2, "amount": "200.00", "currency": "USD"},
            ],
            "categories": [],
        }

        csv_packages = GDPRService.export_to_csv(export_data)
        assert "expenses" in csv_packages
        assert "id,amount,currency" in csv_packages["expenses"]
        assert csv_packages["categories"] == ""
