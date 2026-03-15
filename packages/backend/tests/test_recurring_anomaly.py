"""Tests for recurring transaction anomaly alerts."""

import pytest
from decimal import Decimal
from app.models import (
    RecurringExpense,
    RecurringExpenseSnapshot,
    RecurringAnomalyAlert,
    User,
    Category,
)
from app.extensions import db
from app.services.recurring_anomaly import (
    record_snapshot,
    get_snapshots,
    get_expected_amount,
    check_anomaly,
    scan_all_recurring,
    get_alerts,
    acknowledge_alert,
    acknowledge_all_alerts,
    get_anomaly_summary,
)


# ── Helpers ───────────────────────────────────────────────────────


def _create_user(email="anomaly@test.com"):
    from werkzeug.security import generate_password_hash
    user = User(email=email, password_hash=generate_password_hash("pass123"))
    db.session.add(user)
    db.session.commit()
    return user


def _create_recurring(user_id, amount=100.00, notes="Netflix", active=True):
    from datetime import date
    rec = RecurringExpense(
        user_id=user_id,
        amount=Decimal(str(amount)),
        notes=notes,
        cadence="MONTHLY",
        start_date=date.today(),
        active=active,
    )
    db.session.add(rec)
    db.session.commit()
    return rec


# ── Service: snapshots ────────────────────────────────────────────


class TestSnapshots:
    def test_record_snapshot(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id)
            result = record_snapshot(rec.id, Decimal("100.00"))
            assert result["amount"] == 100.0
            assert result["recurring_id"] == rec.id

    def test_get_snapshots(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id)
            record_snapshot(rec.id, Decimal("100.00"))
            record_snapshot(rec.id, Decimal("110.00"))
            result = get_snapshots(rec.id)
            assert len(result) == 2
            # Most recent first
            assert result[0]["amount"] == 110.0

    def test_get_expected_from_snapshot(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            record_snapshot(rec.id, Decimal("105.00"))
            expected = get_expected_amount(rec.id)
            assert float(expected) == 105.0  # snapshot, not original

    def test_get_expected_fallback_to_recurring(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            expected = get_expected_amount(rec.id)
            assert float(expected) == 100.0

    def test_get_expected_not_found(self, app_fixture):
        with app_fixture.app_context():
            expected = get_expected_amount(999)
            assert expected is None


# ── Service: check_anomaly ────────────────────────────────────────


class TestCheckAnomaly:
    def test_not_found(self, app_fixture):
        with app_fixture.app_context():
            result = check_anomaly(999, Decimal("100.00"))
            assert "error" in result

    def test_no_anomaly(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            result = check_anomaly(rec.id, Decimal("105.00"))
            assert result["is_anomaly"] is False
            assert result["deviation_pct"] == 5.0

    def test_anomaly_increase(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            result = check_anomaly(rec.id, Decimal("150.00"))
            assert result["is_anomaly"] is True
            assert result["deviation_pct"] == 50.0
            assert "alert_id" in result
            assert result["alert_type"] == "amount_increase"

    def test_anomaly_decrease(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            result = check_anomaly(rec.id, Decimal("50.00"))
            assert result["is_anomaly"] is True
            assert result["alert_type"] == "amount_decrease"

    def test_custom_threshold(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            # 15% change with 20% threshold = not anomaly
            result = check_anomaly(rec.id, Decimal("115.00"), threshold_pct=20.0)
            assert result["is_anomaly"] is False

    def test_records_snapshot(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            check_anomaly(rec.id, Decimal("105.00"))
            snaps = get_snapshots(rec.id)
            assert len(snaps) == 1
            assert snaps[0]["amount"] == 105.0

    def test_zero_expected(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=0)
            result = check_anomaly(rec.id, Decimal("50.00"))
            assert result["deviation_pct"] == 100.0


# ── Service: scan_all_recurring ───────────────────────────────────


class TestScanAllRecurring:
    def test_no_recurring(self, app_fixture):
        with app_fixture.app_context():
            result = scan_all_recurring(999)
            assert result["total_checked"] == 0
            assert result["anomalies_found"] == 0

    def test_scan_with_anomaly(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            # Record snapshot at 100, then change amount to 150
            record_snapshot(rec.id, Decimal("100.00"))
            rec.amount = Decimal("150.00")
            db.session.commit()
            result = scan_all_recurring(user.id)
            assert result["total_checked"] == 1
            assert result["anomalies_found"] == 1

    def test_scan_no_anomaly(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            record_snapshot(rec.id, Decimal("100.00"))
            result = scan_all_recurring(user.id)
            assert result["anomalies_found"] == 0

    def test_inactive_excluded(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00, active=False)
            record_snapshot(rec.id, Decimal("100.00"))
            rec.amount = Decimal("200.00")
            db.session.commit()
            result = scan_all_recurring(user.id)
            assert result["total_checked"] == 0


# ── Service: alerts ───────────────────────────────────────────────


class TestAlerts:
    def test_empty_alerts(self, app_fixture):
        with app_fixture.app_context():
            result = get_alerts(999)
            assert result == []

    def test_get_alerts_after_anomaly(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            check_anomaly(rec.id, Decimal("200.00"))
            result = get_alerts(user.id)
            assert len(result) == 1

    def test_unacknowledged_filter(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            check_anomaly(rec.id, Decimal("200.00"))
            alerts = get_alerts(user.id)
            acknowledge_alert(user.id, alerts[0]["id"])
            result = get_alerts(user.id, unacknowledged_only=True)
            assert len(result) == 0

    def test_acknowledge_alert(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            check_anomaly(rec.id, Decimal("200.00"))
            alerts = get_alerts(user.id)
            result = acknowledge_alert(user.id, alerts[0]["id"])
            assert result["acknowledged"] is True

    def test_acknowledge_not_found(self, app_fixture):
        with app_fixture.app_context():
            result = acknowledge_alert(1, 999)
            assert "error" in result

    def test_acknowledge_all(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            check_anomaly(rec.id, Decimal("200.00"))
            # Change amount for second anomaly check
            rec.amount = Decimal("100.00")
            db.session.commit()
            check_anomaly(rec.id, Decimal("300.00"))
            result = acknowledge_all_alerts(user.id)
            assert result["acknowledged_count"] == 2


# ── Service: summary ─────────────────────────────────────────────


class TestAnomalySummary:
    def test_empty_summary(self, app_fixture):
        with app_fixture.app_context():
            result = get_anomaly_summary(999)
            assert result["total_alerts"] == 0

    def test_summary_with_data(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user()
            rec = _create_recurring(user.id, amount=100.00)
            check_anomaly(rec.id, Decimal("200.00"))
            result = get_anomaly_summary(user.id)
            assert result["total_alerts"] == 1
            assert result["unacknowledged"] == 1
            assert "amount_increase" in result["by_type"]
            assert result["max_deviation_pct"] == 100.0


# ── Routes ────────────────────────────────────────────────────────


class TestRecurringAnomalyRoutes:
    def _setup(self, app_fixture):
        with app_fixture.app_context():
            user = _create_user("routeuser@test.com")
            rec = _create_recurring(user.id, amount=100.00)
            return rec.id

    def test_check_anomaly(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            # Need to create a recurring for the auth user
            from app.models import User
            user = User.query.filter_by(email="test@example.com").first()
            rec = _create_recurring(user.id, amount=100.00)
            rec_id = rec.id

        r = client.post("/recurring-anomalies/check",
                        json={"recurring_id": rec_id, "amount": 150.0},
                        headers=auth_header)
        assert r.status_code == 200

    def test_check_missing_fields(self, client, auth_header):
        r = client.post("/recurring-anomalies/check",
                        json={},
                        headers=auth_header)
        assert r.status_code == 400

    def test_scan(self, client, auth_header):
        r = client.post("/recurring-anomalies/scan",
                        json={},
                        headers=auth_header)
        assert r.status_code == 200

    def test_get_alerts(self, client, auth_header):
        r = client.get("/recurring-anomalies/alerts",
                       headers=auth_header)
        assert r.status_code == 200

    def test_ack_alert_not_found(self, client, auth_header):
        r = client.post("/recurring-anomalies/alerts/999/acknowledge",
                        headers=auth_header)
        assert r.status_code == 404

    def test_ack_all(self, client, auth_header):
        r = client.post("/recurring-anomalies/alerts/acknowledge-all",
                        headers=auth_header)
        assert r.status_code == 200

    def test_summary(self, client, auth_header):
        r = client.get("/recurring-anomalies/summary",
                       headers=auth_header)
        assert r.status_code == 200

    def test_snapshots(self, client, auth_header):
        r = client.get("/recurring-anomalies/snapshots/1",
                       headers=auth_header)
        assert r.status_code == 200

    def test_unauthorized(self, client):
        r = client.get("/recurring-anomalies/alerts")
        assert r.status_code == 401
