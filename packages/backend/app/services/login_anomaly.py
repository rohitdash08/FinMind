"""Login Anomaly Detection & Suspicious Activity Alerts.

Features:
- Location-based anomaly detection
- Time-based anomaly detection
- Device fingerprinting
- Brute force detection
- Rate limiting with progressive delays
- Alert system for suspicious activity
"""

import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.login_anomaly")


class LoginAnomalyService:

    def __init__(self):
        self.login_history = defaultdict(list)  # user_id -> list of login records
        self.failed_attempts = defaultdict(list)  # ip -> list of timestamps
        self.device_fingerprints = defaultdict(set)  # user_id -> set of fingerprints
        self.alerts = defaultdict(list)  # user_id -> list of alerts

    def record_login(self, user_id: str, ip: str, user_agent: str,
                      location: str = None, latitude: float = None,
                      longitude: float = None) -> dict:
        """Record a login event and check for anomalies."""
        fingerprint = self._fingerprint(user_agent, ip)
        now = datetime.utcnow()

        record = {
            "login_id": str(uuid4())[:8],
            "timestamp": now.isoformat(),
            "ip": ip,
            "user_agent": user_agent,
            "location": location,
            "latitude": latitude,
            "longitude": longitude,
            "fingerprint": fingerprint,
        }

        self.login_history[user_id].append(record)
        self.device_fingerprints[user_id].add(fingerprint)

        # Check anomalies
        anomalies = self._check_anomalies(user_id, record)

        return {
            "status": "login_recorded",
            "fingerprint": fingerprint,
            "new_device": fingerprint not in (self.device_fingerprints[user_id] - {fingerprint}),
            "anomalies": anomalies,
            "risk_level": self._calculate_risk(anomalies),
            "total_devices": len(self.device_fingerprints[user_id]),
            "total_logins": len(self.login_history[user_id]),
        }

    def record_failed_login(self, ip: str, user_id: str = None) -> dict:
        """Record a failed login attempt."""
        now = datetime.utcnow()
        self.failed_attempts[ip].append(now.isoformat())

        # Clean old attempts (keep last hour)
        cutoff = (now - timedelta(hours=1)).isoformat()
        self.failed_attempts[ip] = [
            t for t in self.failed_attempts[ip] if t > cutoff
        ]

        recent = len(self.failed_attempts[ip])

        # Progressive lockout
        if recent >= 20:
            lockout_minutes = 60
        elif recent >= 10:
            lockout_minutes = 15
        elif recent >= 5:
            lockout_minutes = 5
        else:
            lockout_minutes = 0

        if lockout_minutes > 0:
            logger.warning(f"Brute force detected from {ip}: {recent} attempts")
            self._create_alert(
                ip, "brute_force",
                f"{recent} failed login attempts from {ip}",
                "critical",
            )

        return {
            "failed_count": recent,
            "lockout_minutes": lockout_minutes,
            "is_locked_out": lockout_minutes > 0,
        }

    def get_login_history(self, user_id: str, limit: int = 20) -> dict:
        """Get login history for a user."""
        records = self.login_history.get(user_id, [])

        return {
            "total_logins": len(records),
            "recent": records[-limit:],
            "unique_ips": len(set(r["ip"] for r in records)),
            "unique_devices": len(self.device_fingerprints.get(user_id, set())),
            "first_login": records[0]["timestamp"] if records else None,
            "last_login": records[-1]["timestamp"] if records else None,
        }

    def get_alerts(self, user_id: str, severity: str = None) -> dict:
        """Get security alerts for a user."""
        alerts = self.alerts.get(user_id, [])
        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]

        return {
            "total_alerts": len(alerts),
            "alerts": sorted(alerts, key=lambda x: x["timestamp"], reverse=True),
        }

    def trust_device(self, user_id: str, fingerprint: str) -> dict:
        """Mark a device as trusted."""
        # In production, this would persist to database
        return {
            "status": "device_trusted",
            "user_id": user_id,
            "fingerprint": fingerprint,
        }

    def _check_anomalies(self, user_id: str, record: dict) -> list:
        """Check for anomalous login patterns."""
        anomalies = []
        history = self.login_history[user_id]

        if len(history) < 2:
            return anomalies

        prev = history[-2]

        # Location anomaly
        if record.get("latitude") and prev.get("latitude"):
            distance = self._haversine_km(
                record["latitude"], record["longitude"],
                prev["latitude"], prev["longitude"],
            )
            time_diff = (datetime.fromisoformat(record["timestamp"]) -
                        datetime.fromisoformat(prev["timestamp"])).total_seconds() / 3600

            if distance > 500 and time_diff < 6:
                anomalies.append({
                    "type": "impossible_travel",
                    "severity": "high",
                    "details": f"Login from {distance:.0f}km away within {time_diff:.1f}h",
                    "prev_location": prev.get("location"),
                    "new_location": record.get("location"),
                })

        # Time anomaly (login at unusual hour)
        hour = datetime.fromisoformat(record["timestamp"]).hour
        usual_hours = [datetime.fromisoformat(h["timestamp"]).hour for h in history[:-1]]
        if usual_hours:
            avg_hour = sum(usual_hours) / len(usual_hours)
            if abs(hour - avg_hour) > 6 and hour < 5:
                anomalies.append({
                    "type": "unusual_time",
                    "severity": "medium",
                    "details": f"Login at {hour}:00, usual time around {avg_hour:.0f}:00",
                })

        # New device
        if len(history) > 5 and record["fingerprint"] not in set(
            h["fingerprint"] for h in history[:-1]
        ):
            anomalies.append({
                "type": "new_device",
                "severity": "low",
                "details": "Login from a new device/browser",
            })

        # New IP
        known_ips = set(h["ip"] for h in history[:-1])
        if record["ip"] not in known_ips and len(known_ips) > 3:
            anomalies.append({
                "type": "new_ip",
                "severity": "low",
                "details": f"Login from new IP: {record['ip']}",
            })

        return anomalies

    def _calculate_risk(self, anomalies: list) -> str:
        if not anomalies:
            return "low"
        severities = [a["severity"] for a in anomalies]
        if "high" in severities:
            return "high"
        if "medium" in severities:
            return "medium"
        return "low"

    def _fingerprint(self, user_agent: str, ip: str) -> str:
        raw = f"{user_agent}:{ip.split('.')[0]}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _haversine_km(self, lat1, lon1, lat2, lon2) -> float:
        from math import radians, cos, sin, asin, sqrt
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        return 6371 * 2 * asin(sqrt(a))

    def _create_alert(self, user_id: str, alert_type: str,
                       message: str, severity: str):
        self.alerts[user_id].append({
            "alert_id": str(uuid4())[:8],
            "type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat(),
        })
