"""Tests for recurring transaction anomaly alerts (Issue #108)."""

from datetime import date, timedelta
from decimal import Decimal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_recurring(client, auth_header, amount=100.0, description="Netflix"):
    """Create a recurring expense and return its id."""
    r = client.post(
        "/expenses/recurring",
        json={
            "amount": amount,
            "description": description,
            "cadence": "MONTHLY",
            "start_date": (date.today() - timedelta(days=180)).isoformat(),
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    return r.get_json()["id"]


def _generate_expenses_with_anomaly(
    client, auth_header, app_fixture, recurring_id, amounts
):
    """Manually insert expenses linked to a recurring series with given amounts."""
    from app.extensions import db
    from app.models import Expense

    base_date = date.today() - timedelta(days=30 * len(amounts))
    with app_fixture.app_context():
        for i, amt in enumerate(amounts):
            e = Expense(
                user_id=1,
                amount=Decimal(str(amt)),
                currency="INR",
                expense_type="EXPENSE",
                notes="test-recurring",
                spent_at=base_date + timedelta(days=30 * i),
                source_recurring_id=recurring_id,
            )
            db.session.add(e)
        db.session.commit()


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class TestAnomalyEndpoint:
    def test_no_anomalies_when_empty(self, client, auth_header):
        r = client.get("/anomalies", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert body["count"] == 0
        assert body["anomalies"] == []

    def test_no_anomalies_with_consistent_amounts(
        self, client, auth_header, app_fixture
    ):
        rec_id = _create_recurring(client, auth_header, amount=50.0)
        # All amounts identical — no anomaly
        _generate_expenses_with_anomaly(
            client, auth_header, app_fixture, rec_id,
            [50.0, 50.0, 50.0, 50.0, 50.0],
        )
        r = client.get("/anomalies", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["count"] == 0

    def test_detects_spike_anomaly(self, client, auth_header, app_fixture):
        rec_id = _create_recurring(client, auth_header, amount=100.0)
        # Normal amounts then a big spike
        _generate_expenses_with_anomaly(
            client, auth_header, app_fixture, rec_id,
            [100.0, 100.0, 100.0, 100.0, 500.0],
        )
        r = client.get("/anomalies", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert body["count"] >= 1
        anomaly = body["anomalies"][0]
        assert anomaly["recurring_expense_id"] == rec_id
        assert anomaly["actual_amount"] == 500.0
        assert anomaly["expected_amount"] == 100.0
        assert anomaly["deviation_pct"] > 0
        assert anomaly["severity"] in ("warning", "critical")

    def test_detects_drop_anomaly(self, client, auth_header, app_fixture):
        rec_id = _create_recurring(client, auth_header, amount=200.0)
        # Normal amounts then a big drop
        _generate_expenses_with_anomaly(
            client, auth_header, app_fixture, rec_id,
            [200.0, 200.0, 200.0, 200.0, 10.0],
        )
        r = client.get("/anomalies", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert body["count"] >= 1
        anomaly = body["anomalies"][0]
        assert anomaly["actual_amount"] == 10.0

    def test_sensitivity_parameter(self, client, auth_header, app_fixture):
        rec_id = _create_recurring(client, auth_header, amount=100.0)
        # Moderate variation — only flagged with low sensitivity
        _generate_expenses_with_anomaly(
            client, auth_header, app_fixture, rec_id,
            [100.0, 102.0, 98.0, 101.0, 130.0],
        )
        # High sensitivity (low threshold) should catch it
        r = client.get("/anomalies?sensitivity=1.0", headers=auth_header)
        assert r.status_code == 200
        low_thresh = r.get_json()["count"]

        # Default sensitivity may or may not catch it
        r = client.get("/anomalies?sensitivity=5.0", headers=auth_header)
        assert r.status_code == 200
        high_thresh = r.get_json()["count"]

        assert low_thresh >= high_thresh

    def test_since_filter(self, client, auth_header, app_fixture):
        rec_id = _create_recurring(client, auth_header, amount=100.0)
        _generate_expenses_with_anomaly(
            client, auth_header, app_fixture, rec_id,
            [100.0, 100.0, 100.0, 100.0, 500.0],
        )
        # Filter to future date — should find nothing
        future = (date.today() + timedelta(days=365)).isoformat()
        r = client.get(f"/anomalies?since={future}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["count"] == 0

    def test_invalid_sensitivity_rejected(self, client, auth_header):
        r = client.get("/anomalies?sensitivity=abc", headers=auth_header)
        assert r.status_code == 400

    def test_invalid_since_rejected(self, client, auth_header):
        r = client.get("/anomalies?since=not-a-date", headers=auth_header)
        assert r.status_code == 400

    def test_anomaly_response_structure(self, client, auth_header, app_fixture):
        rec_id = _create_recurring(client, auth_header, amount=100.0)
        _generate_expenses_with_anomaly(
            client, auth_header, app_fixture, rec_id,
            [100.0, 100.0, 100.0, 100.0, 999.0],
        )
        r = client.get("/anomalies", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "count" in body
        assert "anomalies" in body
        if body["count"] > 0:
            a = body["anomalies"][0]
            required_keys = {
                "recurring_expense_id", "expense_id", "description",
                "expected_amount", "actual_amount", "deviation_pct",
                "spent_at", "severity",
            }
            assert required_keys.issubset(a.keys())
