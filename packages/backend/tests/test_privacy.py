import pytest
import json
import zipfile
import io
from app.models import User, AuditLog


class TestPrivacyExport:
    """Tests for the data export endpoint (GDPR compliance)"""

    def test_export_requires_auth(self, client):
        """Export endpoint should require authentication"""
        response = client.get("/privacy/export")
        assert response.status_code == 401

    def test_export_generates_zip_file(self, client, auth_header):
        """Export should return a ZIP file containing user data"""
        response = client.get("/privacy/export", headers=auth_header)
        assert response.status_code == 200
        assert response.content_type == "application/zip"
        
        # Verify it's a valid ZIP file
        zip_data = io.BytesIO(response.data)
        with zipfile.ZipFile(zip_data, 'r') as zip_file:
            # Should contain JSON export
            assert 'user_data.json' in zip_file.namelist()
            
            # Read and verify JSON content
            json_data = json.loads(zip_file.read('user_data.json'))
            assert 'user' in json_data
            assert 'email' in json_data['user']
            assert 'export_date' in json_data

    def test_export_includes_user_data(self, client, auth_header):
        """Export should include all user data"""
        response = client.get("/privacy/export", headers=auth_header)
        assert response.status_code == 200
        
        zip_data = io.BytesIO(response.data)
        with zipfile.ZipFile(zip_data, 'r') as zip_file:
            json_data = json.loads(zip_file.read('user_data.json'))
            
            # Verify user info
            assert json_data['user']['email'] == 'test@example.com'
            
            # Verify all data sections exist
            assert 'categories' in json_data
            assert 'expenses' in json_data
            assert 'recurring_expenses' in json_data
            assert 'bills' in json_data
            assert 'reminders' in json_data
            assert 'ad_impressions' in json_data
            assert 'subscriptions' in json_data

    def test_export_logs_audit_trail(self, client, auth_header, app_fixture):
        """Export should be logged in audit trail"""
        # Get user ID from the auth token
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email='test@example.com').first()
            user_id = user.id
        
        response = client.get("/privacy/export", headers=auth_header)
        assert response.status_code == 200
        
        # Check audit log
        with app_fixture.app_context():
            audit_log = AuditLog.query.filter_by(user_id=user_id).filter(
                AuditLog.action.contains("DATA_EXPORT")
            ).first()
            assert audit_log is not None
            assert "DATA_EXPORT" in audit_log.action


class TestPrivacyDelete:
    """Tests for the account deletion endpoint (GDPR compliance)"""

    def test_delete_request_requires_auth(self, client):
        """Delete request endpoint should require authentication"""
        response = client.post("/privacy/delete/request", json={})
        assert response.status_code == 401

    def test_delete_request_requires_confirmation(self, client, auth_header):
        """Delete request should require explicit confirmation"""
        # Missing confirmation
        response = client.post("/privacy/delete/request", json={}, headers=auth_header)
        assert response.status_code == 400
        
        # Wrong confirmation
        response = client.post(
            "/privacy/delete/request",
            json={"confirmation": "wrong text"},
            headers=auth_header
        )
        assert response.status_code == 400
        
        # Correct confirmation
        response = client.post(
            "/privacy/delete/request",
            json={"confirmation": "delete my account"},
            headers=auth_header
        )
        assert response.status_code == 202

    def test_delete_confirm_requires_auth(self, client):
        """Delete confirm endpoint should require authentication"""
        response = client.post("/privacy/delete/confirm", json={})
        assert response.status_code == 401

    def test_delete_confirm_requires_final_confirmation(self, client, auth_header):
        """Delete confirm should require explicit final confirmation"""
        # Wrong confirmation
        response = client.post(
            "/privacy/delete/confirm",
            json={"final_confirmation": "wrong text"},
            headers=auth_header
        )
        assert response.status_code == 400
        
        # Correct confirmation
        response = client.post(
            "/privacy/delete/confirm",
            json={"final_confirmation": "i understand this is irreversible"},
            headers=auth_header
        )
        assert response.status_code == 200

    def test_delete_removes_user_data(self, client, auth_header, app_fixture):
        """Delete should permanently remove all user data"""
        from app.extensions import db
        
        # Get user ID before deletion
        with app_fixture.app_context():
            user_before = db.session.query(User).filter_by(email='test@example.com').first()
            assert user_before is not None
            user_id = user_before.id
        
        # Perform deletion
        response = client.post(
            "/privacy/delete/confirm",
            json={"final_confirmation": "i understand this is irreversible"},
            headers=auth_header
        )
        assert response.status_code == 200
        
        # Verify user is deleted
        with app_fixture.app_context():
            user_after = db.session.query(User).filter_by(id=user_id).first()
            assert user_after is None

    def test_delete_logs_audit_trail(self, client, auth_header, app_fixture):
        """Delete should be logged in audit trail"""
        from app.extensions import db

        # Get user ID
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email='test@example.com').first()
            user_id = user.id

        # First request deletion (creates DELETION_REQUESTED audit log)
        response = client.post(
            "/privacy/delete/request",
            json={"confirmation": "delete my account"},
            headers=auth_header
        )
        assert response.status_code == 202

        # Verify the request was logged before confirming
        with app_fixture.app_context():
            requested_log = AuditLog.query.filter_by(user_id=user_id).filter(
                AuditLog.action.contains("DELETION_REQUESTED")
            ).first()
            assert requested_log is not None

        # Then confirm deletion
        response = client.post(
            "/privacy/delete/confirm",
            json={"final_confirmation": "i understand this is irreversible"},
            headers=auth_header
        )
        assert response.status_code == 200

        # Check completion audit log
        with app_fixture.app_context():
            completed_log = AuditLog.query.filter(
                AuditLog.action.contains("DELETION_COMPLETED")
            ).first()
            assert completed_log is not None
            assert "permanently deleted" in completed_log.action


class TestPrivacyDeleteStatus:
    """Tests for the deletion status endpoint"""

    def test_delete_status_requires_auth(self, client):
        """Delete status endpoint should require authentication"""
        response = client.get("/privacy/delete/status")
        assert response.status_code == 401

    def test_delete_status_returns_active_account(self, client, auth_header):
        """Delete status should show account is active by default"""
        response = client.get("/privacy/delete/status", headers=auth_header)
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['deletion_requested'] == False
        assert data['deletion_completed'] == False
        assert data['message'] == "Account is active"

    def test_delete_status_shows_requested(self, client, auth_header, app_fixture):
        """Delete status should show deletion requested after request"""
        from app.extensions import db
        
        # Get user ID
        with app_fixture.app_context():
            user = db.session.query(User).filter_by(email='test@example.com').first()
            user_id = user.id
        
        # Request deletion
        response = client.post(
            "/privacy/delete/request",
            json={"confirmation": "delete my account"},
            headers=auth_header
        )
        assert response.status_code == 202
        
        # Check status
        response = client.get("/privacy/delete/status", headers=auth_header)
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['deletion_requested'] == True
        assert data['deletion_completed'] == False


# Import db for tests
from app.extensions import db
