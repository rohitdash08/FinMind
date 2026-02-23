from datetime import datetime, timedelta
import logging
from ..extensions import db
from ..models import LoginEvent, LoginAnomaly, AnomalyType, Severity

logger = logging.getLogger("finmind.security")

# Thresholds
FAILED_LOGIN_THRESHOLD = 5  # failed attempts in the window
FAILED_LOGIN_WINDOW_MINUTES = 15
ODD_HOUR_START = 2  # 2 AM
ODD_HOUR_END = 5  # 5 AM


def record_login_event(
    email: str,
    ip_address: str,
    user_agent: str | None,
    success: bool,
    user_id: int | None = None,
) -> LoginEvent:
    event = LoginEvent(
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
    )
    db.session.add(event)
    db.session.flush()

    if user_id and success:
        _check_new_ip(event, user_id)
        _check_new_device(event, user_id)
        _check_odd_hour(event, user_id)

    if not success:
        _check_brute_force(email, ip_address)

    db.session.commit()
    return event


def _check_new_ip(event: LoginEvent, user_id: int) -> None:
    known_ips = (
        db.session.query(LoginEvent.ip_address)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success.is_(True),
            LoginEvent.id != event.id,
        )
        .distinct()
        .all()
    )
    known_set = {row[0] for row in known_ips}
    if known_set and event.ip_address not in known_set:
        anomaly = LoginAnomaly(
            user_id=user_id,
            login_event_id=event.id,
            anomaly_type=AnomalyType.NEW_IP.value,
            severity=Severity.MEDIUM.value,
            details=f"Login from new IP address: {event.ip_address}",
        )
        db.session.add(anomaly)
        logger.warning(
            "Anomaly: new IP %s for user_id=%s", event.ip_address, user_id
        )


def _check_new_device(event: LoginEvent, user_id: int) -> None:
    if not event.user_agent:
        return
    known_agents = (
        db.session.query(LoginEvent.user_agent)
        .filter(
            LoginEvent.user_id == user_id,
            LoginEvent.success.is_(True),
            LoginEvent.user_agent.isnot(None),
            LoginEvent.id != event.id,
        )
        .distinct()
        .all()
    )
    known_set = {row[0] for row in known_agents}
    if known_set and event.user_agent not in known_set:
        anomaly = LoginAnomaly(
            user_id=user_id,
            login_event_id=event.id,
            anomaly_type=AnomalyType.NEW_DEVICE.value,
            severity=Severity.LOW.value,
            details=f"Login from new device: {event.user_agent[:200]}",
        )
        db.session.add(anomaly)
        logger.info(
            "Anomaly: new device for user_id=%s", user_id
        )


def _check_odd_hour(event: LoginEvent, user_id: int) -> None:
    hour = event.created_at.hour
    if ODD_HOUR_START <= hour < ODD_HOUR_END:
        anomaly = LoginAnomaly(
            user_id=user_id,
            login_event_id=event.id,
            anomaly_type=AnomalyType.ODD_HOUR.value,
            severity=Severity.LOW.value,
            details=f"Login at unusual hour: {hour:02d}:00 UTC",
        )
        db.session.add(anomaly)
        logger.info(
            "Anomaly: odd-hour login for user_id=%s at %02d:00", user_id, hour
        )


def _check_brute_force(email: str, ip_address: str) -> None:
    cutoff = datetime.utcnow() - timedelta(minutes=FAILED_LOGIN_WINDOW_MINUTES)
    recent_failures = (
        db.session.query(LoginEvent)
        .filter(
            LoginEvent.email == email,
            LoginEvent.success.is_(False),
            LoginEvent.created_at >= cutoff,
        )
        .count()
    )
    if recent_failures >= FAILED_LOGIN_THRESHOLD:
        # Find the user if they exist
        from ..models import User

        user = db.session.query(User).filter_by(email=email).first()
        if not user:
            return
        # Avoid duplicate brute-force alerts in the same window
        existing = (
            db.session.query(LoginAnomaly)
            .filter(
                LoginAnomaly.user_id == user.id,
                LoginAnomaly.anomaly_type == AnomalyType.BRUTE_FORCE.value,
                LoginAnomaly.created_at >= cutoff,
            )
            .first()
        )
        if existing:
            return
        anomaly = LoginAnomaly(
            user_id=user.id,
            anomaly_type=AnomalyType.BRUTE_FORCE.value,
            severity=Severity.HIGH.value,
            details=(
                f"Brute force detected: {recent_failures} failed attempts "
                f"from IP {ip_address} in {FAILED_LOGIN_WINDOW_MINUTES} minutes"
            ),
        )
        db.session.add(anomaly)
        logger.warning(
            "Anomaly: brute force on email=%s from IP=%s", email, ip_address
        )


def get_login_history(user_id: int, limit: int = 50) -> list[dict]:
    events = (
        db.session.query(LoginEvent)
        .filter(LoginEvent.user_id == user_id)
        .order_by(LoginEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "ip_address": e.ip_address,
            "user_agent": e.user_agent,
            "success": e.success,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


def get_anomalies(user_id: int, unacknowledged_only: bool = False) -> list[dict]:
    q = db.session.query(LoginAnomaly).filter(LoginAnomaly.user_id == user_id)
    if unacknowledged_only:
        q = q.filter(LoginAnomaly.acknowledged.is_(False))
    anomalies = q.order_by(LoginAnomaly.created_at.desc()).all()
    return [
        {
            "id": a.id,
            "anomaly_type": a.anomaly_type,
            "severity": a.severity,
            "details": a.details,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat(),
        }
        for a in anomalies
    ]


def acknowledge_anomaly(anomaly_id: int, user_id: int) -> bool:
    anomaly = db.session.get(LoginAnomaly, anomaly_id)
    if not anomaly or anomaly.user_id != user_id:
        return False
    anomaly.acknowledged = True
    db.session.commit()
    return True
