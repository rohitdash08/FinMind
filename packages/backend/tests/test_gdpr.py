"""Tests for GDPR PII Export & Delete Workflow.

This module tests:
- Data export functionality
- Data deletion with confirmation
- Audit logging
- Preview endpoints
"""

import json
import zipfile
import io
from datetime import datetime

import pytest
from flask import url_for

from app.models import User, Category, Expense, Bill, AuditLog


@pytest.fixture
def auth_headers(client, test_user):
    """Get authentication headers for test user."""
    # Login to get token
    resp = client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "password123"
    })
    data = resp.get_json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_user(app):
    """Create a test user with data."""
    with app.app_context():
        from app.extensions import db
        from werkzeug.security import generate_password_hash
        
        user = User(
            email="test@example.com",
            password_hash=generate_password_hash("password123"),
            preferred_currency="USD"
        )
        db.session.add(user)
        db.session.commit()
        
        # Create some test data
        category = Category(user_id=user.id, name="Test Category")
        db.session.add(category)
        db.session.commit()
        
        expense = Expense(
            user_id=user.id,
            category_id=category.id,
            amount=100.50,
            currency="USD",
            notes="Test expense"
        )
        db.session.add(expense)
        
        bill = Bill(
            user_id=user.id,
            name="Test Bill",
            amount=50.00,
            next_due_date=datetime.now().date(),
            cadence="MONTHLY"
        )
        db.session.add(bill)
        
        db.session.commit()
        
        yield user
        
        # Cleanup
        db.session.query(Expense).filter_by(user_id=user.id).delete()
        db.session.query(Category).filter_by(user_id=user.id).delete()
        db.session.query(Bill).filter_by(user_id=user.id).delete()
        db.session.query(User).filter_by(id=user.id).delete()
        db.session.commit()


class TestGdprInfo:
    """Test GDPR info endpoint (no auth required)."""
    
    def test_gdpr_info_returns_expected_structure(self, client):
        """GDPR info endpoint returns correct structure."""
        resp = client.get("/gdpr/info")
        
        assert resp.status_code == 200
        data = resp.get_json()
        
        assert data["service"] == "FinMind"
        assert "gdpr_compliance" in data
        assert "right_to_access" in data["gdpr_compliance"]
        assert "right_to_erasure" in data["gdpr_compliance"]
        assert "audit_trail" in data["gdpr_compliance"]
        assert "data_retention" in data


class TestGdprExportPreview:
    """Test GDPR export preview endpoint."""
    
    def test_export_preview_requires_auth(self, client):
        """Export preview requires authentication."""
        resp = client.get("/gdpr/export/preview")
        assert resp.status_code == 401
    
    def test_export_preview_returns_data_summary(self, client, test_user, auth_headers):
        """Export preview returns correct data summary."""
        resp = client.get("/gdpr/export/preview", headers=auth_headers)
        
        assert resp.status_code == 200
        data = resp.get_json()
        
        assert "preview_generated_at" in data
        assert "data_categories" in data
        assert data["data_categories"]["profile"] is True
        assert data["data_categories"]["categories"] >= 1
        assert data["data_categories"]["expenses"] >= 1
        assert data["data_categories"]["bills"] >= 1


class TestGdprExport:
    """Test GDPR data export endpoint."""
    
    def test_export_requires_auth(self, client):
        """Export requires authentication."""
        resp = client.get("/gdpr/export")
        assert resp.status_code == 401
    
    def test_export_returns_zip_file(self, client, test_user, auth_headers):
        """Export returns valid ZIP file with user data."""
        resp = client.get("/gdpr/export", headers=auth_headers)
        
        assert resp.status_code == 200
        assert resp.content_type == "application/zip"
        assert "finmind_data_export_" in resp.headers["Content-Disposition"]
        
        # Parse ZIP contents
        zip_file = zipfile.ZipFile(io.BytesIO(resp.data))
        assert "user_data.json" in zip_file.namelist()
        assert "README.txt" in zip_file.namelist()
        
        # Verify JSON data
        json_data = json.loads(zip_file.read("user_data.json"))
        assert "export_metadata" in json_data
        assert json_data["export_metadata"]["format_version"] == "1.0"
        assert json_data["user_profile"]["email"] == "test@example.com"
        assert len(json_data["categories"]) >= 1
        assert len(json_data["expenses"]) >= 1
    
    def test_export_creates_audit_log(self, client, test_user, auth_headers, app):
        """Export creates audit log entry."""
        with app.app_context():
            from app.extensions import db
            
            # Get initial audit log count
            initial_count = AuditLog.query.filter_by(user_id=test_user.id).count()
            
            # Perform export
            resp = client.get("/gdpr/export", headers=auth_headers)
            assert resp.status_code == 200
            
            # Verify audit log was created
            audit_logs = AuditLog.query.filter_by(user_id=test_user.id).all()
            gdpr_logs = [log for log in audit_logs if log.action.startswith("GDPR_")]
            assert len(gdpr_logs) > initial_count


class TestGdprDeletePreview:
    """Test GDPR delete preview endpoint."""
    
    def test_delete_preview_requires_auth(self, client):
        """Delete preview requires authentication."""
        resp = client.get("/gdpr/delete/preview")
        assert resp.status_code == 401
    
    def test_delete_preview_shows_data_to_delete(self, client, test_user, auth_headers):
        """Delete preview shows what data will be deleted."""
        resp = client.get("/gdpr/delete/preview", headers=auth_headers)
        
        assert resp.status_code == 200
        data = resp.get_json()
        
        assert "warning" in data
        assert data["user_email"] == "test@example.com"
        assert "data_to_be_deleted" in data
        assert data["data_to_be_deleted"]["categories_count"] >= 1
        assert data["data_to_be_deleted"]["expenses_count"] >= 1
        assert data["required_confirmation"] == "DELETE_MY_DATA_PERMANENTLY"
        assert "consequences" in data


class TestGdprDelete:
    """Test GDPR data deletion endpoint."""
    
    def test_delete_requires_auth(self, client):
        """Delete requires authentication."""
        resp = client.post("/gdpr/delete")
        assert resp.status_code == 401
    
    def test_delete_requires_confirmation_token(self, client, test_user, auth_headers):
        """Delete requires correct confirmation token."""
        resp = client.post("/gdpr/delete", 
                          headers=auth_headers,
                          json={"confirmation_token": "wrong_token"})
        
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid confirmation token" in data["error"]
    
    def test_delete_with_valid_confirmation_removes_data(self, client, test_user, auth_headers, app):
        """Delete with valid confirmation removes all user data."""
        user_id = test_user.id
        
        with app.app_context():
            from app.extensions import db
            
            # Verify data exists before deletion
            assert User.query.get(user_id) is not None
            assert Expense.query.filter_by(user_id=user_id).count() > 0
            
        # Perform deletion
        resp = client.post("/gdpr/delete",
                          headers=auth_headers,
                          json={"confirmation_token": "DELETE_MY_DATA_PERMANENTLY"})
        
        assert resp.status_code == 200
        data = resp.get_json()
        assert "permanently deleted" in data["message"]
        assert data["deleted_user_email"] == "test@example.com"
        assert "audit_log_id" in data
        
        with app.app_context():
            from app.extensions import db
            
            # Verify user is deleted
            assert User.query.get(user_id) is None
            # Verify related data is deleted
            assert Expense.query.filter_by(user_id=user_id).count() == 0
            assert Category.query.filter_by(user_id=user_id).count() == 0
            assert Bill.query.filter_by(user_id=user_id).count() == 0


class TestGdprAuditLog:
    """Test GDPR audit log endpoint."""
    
    def test_audit_log_requires_auth(self, client):
        """Audit log requires authentication."""
        resp = client.get("/gdpr/audit-log")
        assert resp.status_code == 401
    
    def test_audit_log_returns_gdpr_actions(self, client, test_user, auth_headers, app):
        """Audit log returns GDPR-related actions only."""
        with app.app_context():
            from app.extensions import db
            
            # Create a GDPR audit entry
            audit = AuditLog(
                user_id=test_user.id,
                action="GDPR_TEST_ACTION",
                created_at=datetime.utcnow()
            )
            db.session.add(audit)
            db.session.commit()
        
        resp = client.get("/gdpr/audit-log", headers=auth_headers)
        
        assert resp.status_code == 200
        data = resp.get_json()
        assert "audit_entries" in data
        
        # Verify only GDPR actions are returned
        for entry in data["audit_entries"]:
            assert entry["action"].startswith("GDPR_")


class TestGdprIntegration:
    """Integration tests for complete GDPR workflow."""
    
    def test_complete_export_then_delete_workflow(self, client, auth_headers, app):
        """Test complete workflow: export data, then delete account."""
        with app.app_context():
            from app.extensions import db
            from werkzeug.security import generate_password_hash
            
            # Create fresh test user
            user = User(
                email="workflow@example.com",
                password_hash=generate_password_hash("password123"),
                preferred_currency="EUR"
            )
            db.session.add(user)
            db.session.commit()
            
            # Create test data
            category = Category(user_id=user.id, name="Workflow Category")
            db.session.add(category)
            db.session.commit()
            
            expense = Expense(
                user_id=user.id,
                category_id=category.id,
                amount=999.99,
                currency="EUR",
                notes="Integration test expense"
            )
            db.session.add(expense)
            db.session.commit()
            
            user_id = user.id
        
        # Re-login with new user (in real test, use auth token for this user)
        resp = client.post("/auth/login", json={
            "email": "workflow@example.com",
            "password": "password123"
        })
        token = resp.get_json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Step 1: Preview export
        resp = client.get("/gdpr/export/preview", headers=headers)
        assert resp.status_code == 200
        preview = resp.get_json()
        assert preview["data_categories"]["expenses"] == 1
        
        # Step 2: Export data
        resp = client.get("/gdpr/export", headers=headers)
        assert resp.status_code == 200
        zip_file = zipfile.ZipFile(io.BytesIO(resp.data))
        json_data = json.loads(zip_file.read("user_data.json"))
        assert json_data["user_profile"]["email"] == "workflow@example.com"
        
        # Step 3: Preview deletion
        resp = client.get("/gdpr/delete/preview", headers=headers)
        assert resp.status_code == 200
        delete_preview = resp.get_json()
        assert delete_preview["data_to_be_deleted"]["expenses_count"] == 1
        
        # Step 4: Delete account
        resp = client.post("/gdpr/delete",
                          headers=headers,
                          json={"confirmation_token": "DELETE_MY_DATA_PERMANENTLY"})
        assert resp.status_code == 200
        
        # Step 5: Verify user can no longer access
        resp = client.get("/gdpr/export/preview", headers=headers)
        assert resp.status_code == 401  # User is deleted, token is invalid
        
        with app.app_context():
            from app.extensions import db
            # Verify cleanup
            assert User.query.get(user_id) is None
            assert Expense.query.filter_by(user_id=user_id).count() == 0
            assert Category.query.filter_by(user_id=user_id).count() == 0
