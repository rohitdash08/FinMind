from datetime import date, timedelta

def test_savings_goals_crud(client, auth_header):
    # Initially empty
    r = client.get('/savings-goals', headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Create goal
    payload = {
        'name': 'Vacation Fund',
        'target_amount': 1000.00,
        'current_amount': 0,
        'currency': 'USD',
        'deadline': (date.today() + timedelta(days=90)).isoformat()
    }
    r = client.post('/savings-goals', json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()['id']

    # List has 1
    r = client.get('/savings-goals', headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]['name'] == 'Vacation Fund'

    # Get single goal
    r = client.get(f'/savings-goals/{goal_id}', headers=auth_header)
    assert r.status_code == 200
    goal = r.get_json()
    assert goal['target_amount'] == 1000.0
    assert goal['progress']['percentage'] == 0.0

    # Update goal
    r = client.patch(f'/savings-goals/{goal_id}', json={'current_amount': 500}, headers=auth_header)
    assert r.status_code == 200
    goal = r.get_json()
    assert goal['current_amount'] == 500.0
    assert goal['progress']['percentage'] == 50.0

    # Delete goal
    r = client.delete(f'/savings-goals/{goal_id}', headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()['message'] == 'deleted'

def test_savings_goal_with_milestones(client, auth_header):
    payload = {
        'name': 'Emergency Fund',
        'target_amount': 10000.00,
        'current_amount': 0,
        'milestones': [
            {'name': 'First 1000', 'target_amount': 1000},
            {'name': 'Halfway', 'target_amount': 5000},
            {'name': 'Almost there', 'target_amount': 7500}
        ]
    }
    r = client.post('/savings-goals', json=payload, headers=auth_header)
    assert r.status_code == 201
    goal = r.get_json()
    assert len(goal['milestones']) == 3
    assert all(not m['reached'] for m in goal['milestones'])

def test_contribute_to_goal(client, auth_header):
    # Create goal
    payload = {'name': 'New Car', 'target_amount': 5000, 'current_amount': 0}
    r = client.post('/savings-goals', json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()['id']

    # Add milestone
    r = client.post(f'/savings-goals/{goal_id}/milestones', json={'name': 'Quarter', 'target_amount': 1250}, headers=auth_header)
    assert r.status_code == 201

    # Contribute
    r = client.post(f'/savings-goals/{goal_id}/contribute', json={'amount': 1000}, headers=auth_header)
    assert r.status_code == 200
    goal = r.get_json()
    assert goal['current_amount'] == 1000.0
    assert goal['progress']['percentage'] == 20.0

    # Contribute to reach milestone
    r = client.post(f'/savings-goals/{goal_id}/contribute', json={'amount': 250}, headers=auth_header)
    assert r.status_code == 200
    goal = r.get_json()
    assert 'milestones_completed' in goal
    assert len(goal['milestones_completed']) == 1

def test_goal_completion(client, auth_header):
    payload = {'name': 'Small Goal', 'target_amount': 100, 'current_amount': 0}
    r = client.post('/savings-goals', json=payload, headers=auth_header)
    assert r.status_code == 201
    goal_id = r.get_json()['id']

    # Contribute to complete
    r = client.post(f'/savings-goals/{goal_id}/contribute', json={'amount': 100}, headers=auth_header)
    assert r.status_code == 200
    goal = r.get_json()
    assert goal['completed'] == True
    assert goal['goal_completed'] == True

    # Cannot contribute to completed goal
    r = client.post(f'/savings-goals/{goal_id}/contribute', json={'amount': 50}, headers=auth_header)
    assert r.status_code == 400

def test_savings_dashboard(client, auth_header):
    # Create multiple goals
    client.post('/savings-goals', json={'name': 'Goal 1', 'target_amount': 1000, 'current_amount': 500}, headers=auth_header)
    client.post('/savings-goals', json={'name': 'Goal 2', 'target_amount': 2000, 'current_amount': 0}, headers=auth_header)

    r = client.get('/savings-goals/dashboard', headers=auth_header)
    assert r.status_code == 200
    dashboard = r.get_json()
    assert dashboard['summary']['total_goals'] == 2
    assert dashboard['summary']['active_goals'] == 2
    assert dashboard['summary']['total_target'] == 3000.0
    assert dashboard['summary']['total_saved'] == 500.0
