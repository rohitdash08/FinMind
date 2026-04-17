import pytest


class TestWeeklyDigest:
    def test_weekly_requires_auth(self, client):
        resp = client.get('/digest/weekly')
        assert resp.status_code == 401

    def test_weekly_returns_structure(self, client, auth_headers):
        resp = client.get('/digest/weekly', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'period' in data
        assert 'summary' in data
        assert 'insights' in data
        assert 'category_breakdown' in data
        assert 'comparison_with_last_week' in data
        assert 'upcoming_bills' in data
        assert 'top_transactions' in data
        assert 'week_start' in data['period']
        assert 'week_end' in data['period']

    def test_weekly_summary_fields(self, client, auth_headers):
        resp = client.get('/digest/weekly', headers=auth_headers)
        data = resp.get_json()
        s = data['summary']
        assert 'total_income' in s
        assert 'total_expenses' in s
        assert 'net_flow' in s
        assert 'transaction_count' in s

    def test_weekly_history(self, client, auth_headers):
        resp = client.get('/digest/weekly/history', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'weeks' in data
        assert len(data['weeks']) <= 4
