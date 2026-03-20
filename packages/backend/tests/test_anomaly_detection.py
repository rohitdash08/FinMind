"""Tests for login anomaly detection service."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.services.anomaly_detection import (
    compute_device_fingerprint,
    analyze_login,
    LoginActivity,
    TrustedDevice,
    SecurityAlert,
    _ip_subnet,
)


def test_compute_device_fingerprint_deterministic():
    fp1 = compute_device_fingerprint("1.2.3.4", "Mozilla/5.0")
    fp2 = compute_device_fingerprint("1.2.3.4", "Mozilla/5.0")
    assert fp1 == fp2
    assert len(fp1) == 16


def test_compute_device_fingerprint_varies_by_ua():
    fp1 = compute_device_fingerprint("1.2.3.4", "Mozilla/5.0")
    fp2 = compute_device_fingerprint("1.2.3.4", "Chrome/120")
    assert fp1 != fp2


def test_compute_device_fingerprint_none_inputs():
    fp = compute_device_fingerprint(None, None)
    assert isinstance(fp, str)
    assert len(fp) == 16


def test_ip_subnet_ipv4():
    assert _ip_subnet("192.168.1.100") == "192.168.1"


def test_ip_subnet_none():
    assert _ip_subnet(None) == "unknown"


def test_ip_subnet_ipv6():
    assert _ip_subnet("::1") == "::1"


class TestAnalyzeLogin:
    """Tests for the analyze_login function (requires app context + db)."""

    @pytest.fixture(autouse=True)
    def setup(self, app, db_session, test_user):
        self.user_id = test_user.id

    def test_first_login_is_anomalous(self, app):
        with app.app_context():
            result = analyze_login(
                self.user_id,
                ip_address="10.0.0.1",
                user_agent="TestBrowser/1.0",
            )
            assert result["is_anomalous"] is True
            assert "new_device" in result["reasons"]
            assert result["anomaly_score"] >= 30

    def test_same_device_second_login_not_anomalous(self, app):
        with app.app_context():
            analyze_login(
                self.user_id,
                ip_address="10.0.0.1",
                user_agent="TestBrowser/1.0",
            )
            result = analyze_login(
                self.user_id,
                ip_address="10.0.0.1",
                user_agent="TestBrowser/1.0",
            )
            assert "new_device" not in result["reasons"]

    def test_new_ip_subnet_detected(self, app):
        with app.app_context():
            for _ in range(3):
                analyze_login(
                    self.user_id,
                    ip_address="10.0.0.1",
                    user_agent="TestBrowser/1.0",
                )
            result = analyze_login(
                self.user_id,
                ip_address="192.168.1.50",
                user_agent="TestBrowser/1.0",
            )
            assert "new_ip_subnet" in result["reasons"]

    def test_rapid_failed_attempts(self, app):
        with app.app_context():
            for _ in range(4):
                analyze_login(
                    self.user_id,
                    ip_address="10.0.0.1",
                    user_agent="TestBrowser/1.0",
                    success=False,
                )
            result = analyze_login(
                self.user_id,
                ip_address="10.0.0.1",
                user_agent="TestBrowser/1.0",
                success=False,
            )
            assert "rapid_failed_attempts" in result["reasons"]
            assert result["anomaly_score"] >= 40

    def test_alert_created_for_high_score(self, app):
        with app.app_context():
            for _ in range(4):
                analyze_login(
                    self.user_id,
                    ip_address="10.0.0.1",
                    user_agent="TestBrowser/1.0",
                    success=False,
                )
            result = analyze_login(
                self.user_id,
                ip_address="10.0.0.1",
                user_agent="TestBrowser/1.0",
                success=False,
            )
            assert result["alert_id"] is not None
            alert = SecurityAlert.query.get(result["alert_id"])
            assert alert is not None
            assert alert.severity in ("medium", "high")

    def test_trusted_device_created_on_low_score_login(self, app):
        with app.app_context():
            analyze_login(
                self.user_id,
                ip_address="10.0.0.1",
                user_agent="TestBrowser/1.0",
            )
            device = TrustedDevice.query.filter_by(user_id=self.user_id).first()
            assert device is not None
            assert device.is_trusted is True

    def test_activity_recorded(self, app):
        with app.app_context():
            result = analyze_login(
                self.user_id,
                ip_address="10.0.0.1",
                user_agent="TestBrowser/1.0",
            )
            activity = LoginActivity.query.get(result["activity_id"])
            assert activity is not None
            assert activity.ip_address == "10.0.0.1"
            assert activity.success is True
