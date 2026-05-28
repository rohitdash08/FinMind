"""
Tests for login anomaly detection.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from app.services.anomaly import (
    record_login_attempt,
    get_alerts,
    should_block_login,
    clear_alerts,
    MAX_FAILED_PER_HOUR,
    MAX_FAILED_PER_DAY,
)


@pytest.fixture(autouse=True)
def cleanup_redis():
    yield
    from ..extensions import redis_client
    if redis_client:
        for key in redis_client.scan_iter("finmind:anomaly:*"):
            redis_client.delete(key)


class TestBruteForceDetection:
    def test_no_alerts_on_normal_login(self):
        alerts = record_login_attempt(1, "1.2.3.4", success=True)
        assert alerts == []

    def test_no_alerts_on_few_failures(self):
        for i in range(5):
            record_login_attempt(1, "1.2.3.4", success=False)
        alerts = record_login_attempt(1, "1.2.3.4", success=False)
        # Should not trigger high severity
        high = [a for a in alerts if a.severity == "high"]
        assert len(high) == 0

    def test_medium_alert_on_half_threshold(self):
        for i in range(MAX_FAILED_PER_HOUR // 2):
            record_login_attempt(2, "5.6.7.8", success=False)
        alerts = record_login_attempt(2, "5.6.7.8", success=False)
        types = [a.alert_type for a in alerts]
        assert "brute_force" in types

    def test_high_alert_on_threshold(self):
        for i in range(MAX_FAILED_PER_HOUR):
            record_login_attempt(3, "9.10.11.12", success=False)
        alerts = record_login_attempt(3, "9.10.11.12", success=False)
        high = [a for a in alerts if a.severity == "high"]
        assert len(high) >= 1

    def test_block_on_critical(self):
        for i in range(MAX_FAILED_PER_DAY):
            record_login_attempt(4, "13.14.15.16", success=False)
        assert should_block_login(4) is True


class TestImpossibleTravel:
    def test_no_alert_same_country(self):
        record_login_attempt(10, "1.1.1.1", success=True, country="US", city="NYC")
        alerts = record_login_attempt(10, "2.2.2.2", success=True, country="US", city="LA")
        travel = [a for a in alerts if a.alert_type == "impossible_travel"]
        assert len(travel) == 0  # Same country is OK

    def test_alert_different_country(self):
        record_login_attempt(11, "1.1.1.1", success=True, country="US", city="NYC")
        alerts = record_login_attempt(11, "2.2.2.2", success=True, country="JP", city="Tokyo")
        travel = [a for a in alerts if a.alert_type == "impossible_travel"]
        assert len(travel) >= 1
        assert travel[0].severity == "high"

    def test_no_alert_without_location(self):
        record_login_attempt(12, "1.1.1.1", success=True)
        alerts = record_login_attempt(12, "2.2.2.2", success=True, country="JP", city="Tokyo")
        travel = [a for a in alerts if a.alert_type == "impossible_travel"]
        assert len(travel) == 0


class TestAlertManagement:
    def test_get_alerts_empty(self):
        result = get_alerts(99)
        assert result == []

    def test_get_alerts_after_detection(self):
        for i in range(MAX_FAILED_PER_HOUR):
            record_login_attempt(20, "1.1.1.1", success=False)
        alerts = get_alerts(20)
        assert len(alerts) >= 1

    def test_clear_alerts(self):
        for i in range(MAX_FAILED_PER_HOUR):
            record_login_attempt(21, "1.1.1.1", success=False)
        count = clear_alerts(21)
        assert count >= 1
        assert get_alerts(21) == []

    def test_should_not_block_normal_user(self):
        assert should_block_login(999) is False
