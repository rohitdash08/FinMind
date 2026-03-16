from datetime import date, timedelta
from app.models import Expense
from app.extensions import db

def test_expense_heatmap_logic(client, auth_header):
    # The auth_header fixture creates a user. We need its ID.
    # In conftest.py, the user is registered with test@example.com
    from app.models import User
    user = db.session.query(User).filter_by(email="test@example.com").first()
    uid = user.id
    
    today = date.today()
    
    # 2 expenses today
    db.session.add(Expense(user_id=uid, amount=100, spent_at=today, notes="Test 1", currency="INR", expense_type="EXPENSE"))
    db.session.add(Expense(user_id=uid, amount=50, spent_at=today, notes="Test 2", currency="INR", expense_type="EXPENSE"))
    
    # 1 expense yesterday
    yesterday = today - timedelta(days=1)
    db.session.add(Expense(user_id=uid, amount=200, spent_at=yesterday, notes="Test 3", currency="INR", expense_type="EXPENSE"))
    
    db.session.commit()
    
    response = client.get("/expenses/heatmap?days=7", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    
    # Find today's entry
    today_entry = next((item for item in data if item["date"] == today.isoformat()), None)
    assert today_entry is not None
    assert today_entry["amount"] == 150.0
    assert today_entry["count"] == 2
    
    # Find yesterday's entry
    yesterday_entry = next((item for item in data if item["date"] == yesterday.isoformat()), None)
    assert yesterday_entry is not None
    assert yesterday_entry["amount"] == 200.0
    assert yesterday_entry["count"] == 1
