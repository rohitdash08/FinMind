"""Login anomaly detection & suspicious activity alerts.

Detects unusual login behaviour including:
- IP address changes (new / previously-unseen IPs)
- Device fingerprint changes
- Unusual login hours (configurable quiet window)
- Brute-force / high-frequency login attempts

Alerts are persisted in the database and optionally surfaced via the
``/auth/security-alerts`` endpoint.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..extensions import db, redis_client
from ..models import LoginEvent, SecurityAlert

logger = logging.getLogger("finmind.login_anomaly")

# ---------------------------------------------------------------------------
# Configuration defaults (can be overridden via app.config)
# ---------------------------------------------------------------------------
DEFAULT_QUIET_HOURS_START = 1   # 01:00 UTC
DEFAULT_QUIET_HOURS_END = 5     # 05:00 UTC
MAX_FAILED_ATTEMPTS = 5         # within the rate window
RATE_WINDOW_SECONDS = 300       # 5 minutes
IP_HISTORY_LIMIT = 50           # recent IPs to keep per user


def _device_fingerprint(user_agent: str) -> str:
    """Derive a stable fingerprint from the User-Agent string."""
    return hashlib.sha256(user_agent.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

class AnomalyDetector:
    """Stateless helper that analyses a login attempt and returns alerts."""

    def __init__(
        self,
        quiet_start: int = DEFAULT_QUIET_HOURS_START,
        quiet_end: int = DEFAULT_QUIET_HOURS_END,
    ):
        self.quiet_start = quiet_start
        self.quiet_end = quiet_end

    # -- public API ----------------------------------------------------------

    def analyse(
        self,
        user_id: int,
        ip_address: str,
        user_agent: str,
        login_success: bool,
        now: Optional[datetime] = None,
    ) -> list[dict]:
        """Run all detectors and return a list of alert dicts.

        Each dict has keys: ``alert_type``, ``severity``, ``message``,
        ``metadata``.
        """
        now = now or datetime.now(timezone.utc)
        alerts: list[dict] = []

        fingerprint = _device_fingerprint(user_agent)

        # Record the login event first
        self._record_event(user_id, ip_address, fingerprint, login_success, now)

        if login_success:
            alerts.extend(self._check_new_ip(user_id, ip_address, now))
            alerts.extend(self._check_new_device(user_id, fingerprint, user_agent, now))
            alerts.extend(self._check_unusual_hour(user_id, now))

        alerts.extend(self._check_brute_force(user_id, ip_address, login_success, now))

        # Persist alerts
        for a in alerts:
            self._persist_alert(user_id, a, now)

        return alerts

    # -- individual detectors ------------------------------------------------

    def _check_new_ip(self, user_id: int, ip_address: str, now: datetime) -> list[dict]:
        """Alert when a login comes from a never-before-seen IP."""
        previous = (
            LoginEvent.query
            .filter_by(user_id=user_id, success=True)
            .filter(LoginEvent.ip_address != ip_address)
            .order_by(LoginEvent.created_at.desc())
            .limit(IP_HISTORY_LIMIT)
            .all()
        )
        known_ips = {e.ip_address for e in previous}

        # If user has prior logins but this IP is new
        if known_ips and ip_address not in known_ips:
            return [
                {
                    "alert_type": "new_ip",
                    "severity": "medium",
                    "message": f"Login from new IP address {ip_address}",
                    "metadata": {"ip_address": ip_address},
                }
            ]
        return []

    def _check_new_device(
        self, user_id: int, fingerprint: str, user_agent: str, now: datetime
    ) -> list[dict]:
        """Alert when a login comes from an unrecognised device."""
        previous = (
            LoginEvent.query
            .filter_by(user_id=user_id, success=True)
            .filter(LoginEvent.device_fingerprint != fingerprint)
            .order_by(LoginEvent.created_at.desc())
            .limit(IP_HISTORY_LIMIT)
            .all()
        )
        known_fps = {e.device_fingerprint for e in previous}

        if known_fps and fingerprint not in known_fps:
            return [
                {
                    "alert_type": "new_device",
                    "severity": "medium",
                    "message": "Login from unrecognised device",
                    "metadata": {
                        "device_fingerprint": fingerprint,
                        "user_agent": user_agent[:200],
                    },
                }
            ]
        return []

    def _check_unusual_hour(self, user_id: int, now: datetime) -> list[dict]:
        """Alert when login occurs during the quiet-hours window."""
        hour = now.hour
        if self.quiet_start <= hour < self.quiet_end:
            return [
                {
                    "alert_type": "unusual_hour",
                    "severity": "low",
                    "message": f"Login at unusual hour ({hour:02d}:00 UTC)",
                    "metadata": {"hour_utc": hour},
                }
            ]
        return []

    def _check_brute_force(
        self, user_id: int, ip_address: str, login_success: bool, now: datetime
    ) -> list[dict]:
        """Alert on excessive failed login attempts (rate-limited via Redis)."""
        key = f"login:fail:{ip_address}:{user_id}"

        if not login_success:
            try:
                pipe = redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, RATE_WINDOW_SECONDS)
                results = pipe.execute()
                count = results[0]
            except Exception:
                logger.debug("Redis unavailable; skipping brute-force check")
                return []

            if count and int(count) >= MAX_FAILED_ATTEMPTS:
                return [
                    {
                        "alert_type": "brute_force",
                        "severity": "high",
                        "message": (
                            f"{count} failed login attempts from {ip_address} "
                            f"in the last {RATE_WINDOW_SECONDS}s"
                        ),
                        "metadata": {
                            "ip_address": ip_address,
                            "failed_count": int(count),
                            "window_seconds": RATE_WINDOW_SECONDS,
                        },
                    }
                ]
        else:
            # Reset counter on successful login
            try:
                redis_client.delete(key)
            except Exception:
                pass

        return []

    # -- persistence helpers -------------------------------------------------

    @staticmethod
    def _record_event(
        user_id: int,
        ip_address: str,
        fingerprint: str,
        success: bool,
        now: datetime,
    ) -> LoginEvent:
        event = LoginEvent(
            user_id=user_id,
            ip_address=ip_address,
            device_fingerprint=fingerprint,
            success=success,
            created_at=now,
        )
        db.session.add(event)
        db.session.commit()
        return event

    @staticmethod
    def _persist_alert(user_id: int, alert: dict, now: datetime) -> SecurityAlert:
        sa = SecurityAlert(
            user_id=user_id,
            alert_type=alert["alert_type"],
            severity=alert["severity"],
            message=alert["message"],
            metadata_json=str(alert.get("metadata", {})),
            acknowledged=False,
            created_at=now,
        )
        db.session.add(sa)
        db.session.commit()
        logger.info(
            "Security alert user_id=%s type=%s severity=%s",
            user_id,
            alert["alert_type"],
            alert["severity"],
        )
        return sa
