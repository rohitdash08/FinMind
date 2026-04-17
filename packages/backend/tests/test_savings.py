import pytest


class TestSavingsGoals:
    def test_goals_require_auth(self, client):
        resp = client.get('/savings/goals')
        assert resp.status_code == 401

    def test_create_and_list_goals(self, client, auth_headers):
        resp = client.post('/savings/goals', headers=auth_headers, json={
            'name': 'Emergency Fund',
            'target_amount': 10000,
            'currency': 'USD',
        })
        assert resp.status_code == 201
        goal = resp.get_json()
        assert goal['name'] == 'Emergency Fund'
        assert goal['target_amount'] == 10000

        resp = client.get('/savings/goals', headers=auth_headers)
        assert resp.status_code == 200
        goals = resp.get_json()['goals']
        assert len(goals) >= 1

    def test_create_goal_validation(self, client, auth_headers):
        resp = client.post('/savings/goals', headers=auth_headers, json={})
        assert resp.status_code == 400

        resp = client.post('/savings/goals', headers=auth_headers, json={
            'name': 'Test', 'target_amount': -100
        })
        assert resp.status_code == 400

    def test_milestones(self, client, auth_headers):
        resp = client.post('/savings/goals', headers=auth_headers, json={
            'name': 'Vacation', 'target_amount': 5000
        })
        gid = resp.get_json()['id']

        resp = client.post(f'/savings/goals/{gid}/milestones', headers=auth_headers, json={
            'name': 'First 000', 'amount': 1000
        })
        assert resp.status_code == 201

        resp = client.get(f'/savings/goals/{gid}/milestones', headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.get_json()['milestones']) >= 1

    def test_overview(self, client, auth_headers):
        resp = client.get('/savings/overview', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_target' in data
        assert 'total_saved' in data
        assert 'goals' in data
