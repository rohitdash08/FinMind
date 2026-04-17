import pytest

class TestSecurity:
    def test_alerts_require_auth(self, client):
        resp = client.get('/security/alerts')
        assert resp.status_code == 401

    def test_login_check(self, client, auth_headers):
        resp = client.post('/security/login-check', headers=auth_headers, json={
            'ip': '1.2.3.4', 'user_agent': 'TestBrowser'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'hour_count' in data
        assert 'day_count' in data
        assert 'anomalies' in data

    def test_get_alerts(self, client, auth_headers):
        resp = client.get('/security/alerts', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'recent_anomalies' in data
        assert 'current_stats' in data
        assert 'thresholds' in data
