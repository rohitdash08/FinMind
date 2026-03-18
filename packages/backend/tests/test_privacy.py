"""Tests for privacy/GDPR endpoints."""
import io
import json
import zipfile
import pytest
from app import create_app
from app.extensions import db
from app.models import User, Category, Expense, Bill, AuditLog
from flask_jwt_extended import create_access_token


@pytest.fixture
def app():
    """Create test app with in-memory SQLite database."""
    from app.config import Settings
    
    class TestSettings(Settings):
        database_url = "sqlite:///:memory:"
        jwt_secret = "test-secret-key"
        redis_url = "redis://localhost:6379/15"
        openai_api_key = ""
        gemini_api_key = ""
        gemini_model = ""
        twilio_account_sid = ""
        twilio_auth_token = ""
        twilio_whatsapp_from = ""
        email_from = ""
        jwt_access_minutes = 15
        jwt_refresh_hours = 24
    
    app = create_app(TestSettings())
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def auth_header(app):
    """Create authenticated user and return auth header."""
    with app.app_context():
        from werkzeug.security import generate_password_hash
        
        user = User(
            email="test@example.com",
            password_hash=generate_password_hash("password123"),
            preferred_currency="USD",
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        
        token = create_access_token(identity=str(user_id))
        return {"Authorization": f"Bearer {token}"}, user_id


class TestPrivacyExport:
    """Tests for data export endpoint."""
    
    def test_export_requires_auth(self, client):
        """Export endpoint requires authentication."""
        response = client.get("/privacy/export")
        assert response.status_code == 401
    
    def test_export_returns_zip_file(self, client, auth_header):
        """Export endpoint returns a valid ZIP file."""
        headers, user_id = auth_header
        
        response = client.get("/privacy/export", headers=headers)
        
        assert response.status_code == 200
        assert response.content_type == "application/zip"
        assert "attachment" in response.headers.get("Content-Disposition", "")
        
    def test_export_contains_json_data(self, client, auth_header):
        """Export ZIP contains full_export.json with user data."""
        headers, user_id = auth_header
        
        response = client.get("/privacy/export", headers=headers)
        
        zip_buffer = io.BytesIO(response.data)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            assert "full_export.json" in zf.namelist()
            
            json_data = json.loads(zf.read("full_export.json"))
            assert "user" in json_data
            assert json_data["user"]["id"] == user_id
            assert json_data["user"]["email"] == "test@example.com"
    
    def test_export_includes_expenses(self, client, app, auth_header):
        """Export includes expense data."""
        headers, user_id = auth_header
        
        with app.app_context():
            user = db.session.get(User, user_id)
            category = Category(user_id=user_id, name="Food")
            db.session.add(category)
            db.session.commit()
            
            expense = Expense(
                user_id=user_id,
                category_id=category.id,
                amount=50.00,
                currency="USD",
                notes="Test expense",
            )
            db.session.add(expense)
            db.session.commit()
        
        response = client.get("/privacy/export", headers=headers)
        zip_buffer = io.BytesIO(response.data)
        
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            json_data = json.loads(zf.read("full_export.json"))
            assert len(json_data["expenses"]) == 1
            assert json_data["expenses"][0]["amount"] == 50.00
            assert "expenses.csv" in zf.namelist()
    
    def test_export_creates_audit_log(self, client, app, auth_header):
        """Export creates an audit log entry."""
        headers, user_id = auth_header
        
        with app.app_context():
            initial_count = db.session.query(AuditLog).filter_by(
                user_id=user_id, action="DATA_EXPORT"
            ).count()
        
        client.get("/privacy/export", headers=headers)
        
        with app.app_context():
            final_count = db.session.query(AuditLog).filter_by(
                user_id=user_id, action="DATA_EXPORT"
            ).count()
            assert final_count == initial_count + 1


class TestPrivacyDelete:
    """Tests for account deletion endpoint."""
    
    def test_delete_requires_auth(self, client):
        """Delete endpoint requires authentication."""
        response = client.post("/privacy/delete", json={"confirm": True})
        assert response.status_code == 401
    
    def test_delete_requires_confirmation(self, client, auth_header):
        """Delete requires explicit confirmation."""
        headers, user_id = auth_header
        
        response = client.post("/privacy/delete", headers=headers, json={})
        assert response.status_code == 400
        assert "confirmation" in response.json.get("error", "").lower()
    
    def test_delete_requires_correct_confirmation_text(self, client, auth_header):
        """Delete requires exact confirmation text."""
        headers, user_id = auth_header
        
        response = client.post(
            "/privacy/delete",
            headers=headers,
            json={"confirm": True, "confirmation_text": "WRONG TEXT"}
        )
        assert response.status_code == 400
    
    def test_delete_removes_user(self, client, app, auth_header):
        """Successful deletion removes user account."""
        headers, user_id = auth_header
        
        response = client.post(
            "/privacy/delete",
            headers=headers,
            json={"confirm": True, "confirmation_text": "DELETE MY ACCOUNT"}
        )
        
        assert response.status_code == 200
        assert response.json["deleted"] is True
        
        with app.app_context():
            user = db.session.get(User, user_id)
            assert user is None
    
    def test_delete_removes_all_user_data(self, client, app, auth_header):
        """Deletion removes all associated user data."""
        headers, user_id = auth_header
        
        with app.app_context():
            # Create related data
            category = Category(user_id=user_id, name="Test")
            db.session.add(category)
            db.session.commit()
            
            expense = Expense(
                user_id=user_id,
                amount=100.00,
                currency="USD",
            )
            bill = Bill(
                user_id=user_id,
                name="Test Bill",
                amount=50.00,
                next_due_date="2024-12-31",
                cadence="MONTHLY",
            )
            db.session.add_all([expense, bill])
            db.session.commit()
        
        response = client.post(
            "/privacy/delete",
            headers=headers,
            json={"confirm": True, "confirmation_text": "DELETE MY ACCOUNT"}
        )
        
        assert response.status_code == 200
        assert response.json["records_removed"]["expenses"] == 1
        assert response.json["records_removed"]["bills"] == 1
        assert response.json["records_removed"]["categories"] == 1
    
    def test_delete_creates_audit_log(self, client, app, auth_header):
        """Deletion creates an audit log entry."""
        headers, user_id = auth_header
        
        client.post(
            "/privacy/delete",
            headers=headers,
            json={"confirm": True, "confirmation_text": "DELETE MY ACCOUNT"}
        )
        
        with app.app_context():
            log = db.session.query(AuditLog).filter(
                AuditLog.action.like(f"%ACCOUNT_DELETION%{user_id}%")
            ).first()
            assert log is not None
            assert log.user_id is None  # User ID should be nulled


class TestPrivacyStatus:
    """Tests for privacy status endpoint."""
    
    def test_status_requires_auth(self, client):
        """Status endpoint requires authentication."""
        response = client.get("/privacy/status")
        assert response.status_code == 401
    
    def test_status_returns_privacy_info(self, client, auth_header):
        """Status endpoint returns privacy information."""
        headers, user_id = auth_header
        
        response = client.get("/privacy/status", headers=headers)
        
        assert response.status_code == 200
        assert response.json["user_id"] == user_id
        assert response.json["gdpr_compliant"] is True
        assert response.json["deletion_is_irreversible"] is True
