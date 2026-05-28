"""Tests for Login Anomaly Detection."""

import pytest


class TestLoginAnomaly:
    def test_record_login(self):
        from app.services.login_anomaly import LoginAnomalyService
        svc = LoginAnomalyService()
        result = svc.record_login("u1", "192.168.1.1", "Mozilla/5.0", "NYC", 40.7, -74.0)
        assert result["status"] == "login_recorded"
        assert result["risk_level"] == "low"

    def test_impossible_travel(self):
        from app.services.login_anomaly import LoginAnomalyService
        svc = LoginAnomalyService()
        svc.record_login("u1", "1.1.1.1", "Mozilla", "NYC", 40.7, -74.0)
        # Same time but far away
        result = svc.record_login("u1", "2.2.2.2", "Mozilla", "LA", 34.0, -118.2)
        anomalies = [a for a in result["anomalies"] if a["type"] == "impossible_travel"]
        assert len(anomalies) > 0

    def test_brute_force(self):
        from app.services.login_anomaly import LoginAnomalyService
        svc = LoginAnomalyService()
        for i in range(6):
            result = svc.record_failed_login("10.0.0.1")
        assert result["is_locked_out"] is True

    def test_history(self):
        from app.services.login_anomaly import LoginAnomalyService
        svc = LoginAnomalyService()
        svc.record_login("u1", "1.1.1.1", "Mozilla")
        svc.record_login("u1", "1.1.1.1", "Mozilla")
        history = svc.get_login_history("u1")
        assert history["total_logins"] == 2

    def test_new_device_alert(self):
        from app.services.login_anomaly import LoginAnomalyService
        svc = LoginAnomalyService()
        for i in range(6):
            svc.record_login("u1", "1.1.1.1", "Browser-A", "NYC", 40.7, -74.0)
        result = svc.record_login("u1", "1.1.1.1", "Browser-B", "NYC", 40.7, -74.0)
        types = [a["type"] for a in result["anomalies"]]
        assert "new_device" in types
