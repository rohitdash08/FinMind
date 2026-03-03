import pytest
from app import create_app, db
from app.models import User, Household, HouseholdMember, MemberRole
import json

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def init_database(app):
    with app.app_context():
        # Create test users
        user1 = User(email='user1@test.com', password_hash='hash1')
        user2 = User(email='user2@test.com', password_hash='hash2')
        db.session.add(user1)
        db.session.add(user2)
        db.session.commit()
        yield user1, user2

def test_create_household(client, init_database):
    """Test creating a household."""
    user1, user2 = init_database
    
    # Login (mocked or real depending on auth setup)
    # For now, assume we can bypass auth or use a test token
    # This part depends on your actual auth implementation
    
    response = client.post('/api/households',
                          json={'name': 'Test Household'},
                          headers={'Authorization': 'Bearer test_token'})  # Adjust as needed
    
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['name'] == 'Test Household'
    assert data['role'] == 'admin'

def test_invite_member(client, init_database):
    """Test inviting a member to a household."""
    user1, user2 = init_database
    
    # Create household
    client.post('/api/households', json={'name': 'Test Household'})
    
    # Invite user2
    response = client.post('/api/households/1/invite',
                          json={'email': 'user2@test.com', 'role': 'member'})
    
    assert response.status_code == 201
    data = json.loads(response.data)
    assert 'added' in data['message']

def test_duplicate_member_prevention(client, init_database):
    """Test that duplicate members are prevented."""
    user1, user2 = init_database
    
    # Create household and add user2
    client.post('/api/households', json={'name': 'Test Household'})
    client.post('/api/households/1/invite', json={'email': 'user2@test.com'})
    
    # Try to add again
    response = client.post('/api/households/1/invite',
                          json={'email': 'user2@test.com'})
    
    assert response.status_code == 400
    assert 'already a member' in json.loads(response.data)['error']

def test_list_my_households(client, init_database):
    """Test listing user's households."""
    user1, user2 = init_database
    
    # Create household
    client.post('/api/households', json={'name': 'My Household'})
    
    response = client.get('/api/households/my')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data['households']) == 1
    assert data['households'][0]['name'] == 'My Household'
