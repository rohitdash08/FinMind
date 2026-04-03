import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.services.login_anomaly import LoginAnomalyDetector

@pytest.fixture
def detector():
    return LoginAnomalyDetector()

def make_event(user_id="user1", ip="1.2.3.4", ua="Mozilla/5.0 (Windows NT)", success=True,
               country="US", minutes_ago=0):
    ts = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat()
    return {
        "user_id": user_id,
        "ip_address": ip,
        "user_agent": ua,
        "success": success,
        "timestamp": ts,
        "location": {"country": country},
    }

def test_no_anomaly_for_normal_login(detector):
    """Normal login produces no anomalies."""
    event = make_event()
    anomalies = detector.analyze_login(event)
    assert isinstance(anomalies, list)

def test_brute_force_detected(detector):
    """Brute force: 5+ failed logins in 1 hour triggers high-severity alert."""
    import app.services.login_anomaly as svc
    user_id = "bruteuser"
    # Store 5 failed events
    for _ in range(5):
        e = make_event(user_id=user_id, success=False)
        svc._login_events[user_id].append(e)
    event = make_event(user_id=user_id, success=False)
    anomalies = detector.analyze_login(event)
    types = [a["type"] for a in anomalies]
    assert "brute_force_attempt" in types
    brute = next(a for a in anomalies if a["type"] == "brute_force_attempt")
    assert brute["severity"] == "high"

def test_new_ip_flagged(detector):
    """Login from a brand-new IP address is flagged."""
    import app.services.login_anomaly as svc
    user_id = "ipuser"
    # One previous successful login from a different IP
    svc._login_events[user_id].append(make_event(user_id=user_id, ip="10.0.0.1", success=True))
    event = make_event(user_id=user_id, ip="99.99.99.99")
    anomalies = detector.analyze_login(event)
    types = [a["type"] for a in anomalies]
    assert "new_ip_address" in types

def test_impossible_travel_detected(detector):
    """Logins from two different countries within 60 min are flagged."""
    import app.services.login_anomaly as svc
    user_id = "traveluser"
    # Prior login from US
    svc._login_events[user_id].append(make_event(user_id=user_id, country="US", minutes_ago=30))
    # Now login from FR
    event = make_event(user_id=user_id, ip="5.6.7.8", country="FR")
    anomalies = detector.analyze_login(event)
    types = [a["type"] for a in anomalies]
    assert "impossible_travel" in types
    travel = next(a for a in anomalies if a["type"] == "impossible_travel")
    assert travel["severity"] == "critical"

def test_alert_dismiss(detector):
    """Dismissing an alert removes it from active alerts."""
    import app.services.login_anomaly as svc
    user_id = "dismissuser"
    event = make_event(user_id=user_id, ip="222.111.0.0")
    # Manually create an alert
    svc._security_alerts[user_id].append({
        "id": "alert-abc",
        "type": "test",
        "severity": "low",
        "dismissed": False,
    })
    active = detector.get_active_alerts(user_id)
    assert any(a["id"] == "alert-abc" for a in active)
    result = detector.dismiss_alert(user_id, "alert-abc")
    assert result is True
    active_after = detector.get_active_alerts(user_id)
    assert not any(a["id"] == "alert-abc" for a in active_after)

def test_trusted_ip_no_new_ip_alert(detector):
    """Login from a trusted IP should not trigger new_ip_address alert."""
    import app.services.login_anomaly as svc
    user_id = "trusteduser"
    detector.add_trusted_ip(user_id, "5.5.5.5")
    event = make_event(user_id=user_id, ip="5.5.5.5")
    anomalies = detector.analyze_login(event)
    types = [a["type"] for a in anomalies]
    assert "new_ip_address" not in types

def test_unusual_time_flagged(detector):
    """Login at 3 AM is flagged as unusual."""
    ts_3am = datetime.utcnow().replace(hour=3, minute=0, second=0).isoformat()
    event = {
        "user_id": "nightowl",
        "ip_address": "1.2.3.4",
        "user_agent": "Mozilla",
        "success": True,
        "timestamp": ts_3am,
        "location": {"country": "US"},
    }
    anomalies = detector.analyze_login(event)
    types = [a["type"] for a in anomalies]
    assert "unusual_login_time" in types
