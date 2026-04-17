import pytest


class TestAccounts:
    def test_accounts_require_auth(self, client):
        resp = client.get('/accounts/')
        assert resp.status_code == 401

    def test_create_and_list(self, client, auth_headers):
        resp = client.post('/accounts/', headers=auth_headers, json={
            'name': 'Checking', 'account_type': 'checking', 'currency': 'USD'
        })
        assert resp.status_code == 201
        acc = resp.get_json()
        assert acc['name'] == 'Checking'

        resp = client.get('/accounts/', headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.get_json()['accounts']) >= 1

    def test_overview(self, client, auth_headers):
        resp = client.get('/accounts/overview', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'accounts' in data
        assert 'combined' in data
        assert 'total_income' in data['combined']
