import hashlib
import re
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Optional
import uuid

# In-memory storage (replace with Redis/DB in production)
_login_events: Dict[str, List[Dict]] = defaultdict(list)
_security_alerts: Dict[str, List[Dict]] = defaultdict(list)
_trusted_ips: Dict[str, List[str]] = defaultdict(list)

class LoginAnomalyDetector:
    """Detects suspicious login activity and generates security alerts."""

    # Thresholds
    MAX_FAILED_LOGINS = 5        # per hour
    NEW_LOCATION_ALERT = True
    UNUSUAL_TIME_START = 1       # 1 AM
    UNUSUAL_TIME_END = 5         # 5 AM

    def analyze_login(self, event: Dict) -> List[Dict]:
        """Analyze a login event and return list of anomalies detected."""
        user_id = event["user_id"]
        anomalies = []

        # 1. Brute force: too many failed logins
        if not event.get("success", True):
            failed = self._count_recent_failures(user_id, window_minutes=60)
            if failed >= self.MAX_FAILED_LOGINS:
                anomalies.append({
                    "type": "brute_force_attempt",
                    "severity": "high",
                    "description": f"Too many failed login attempts: {failed} in the last hour",
                    "ip_address": event.get("ip_address"),
                    "timestamp": event.get("timestamp"),
                })

        if not event.get("success", True):
            return anomalies  # No further checks for failed logins

        # 2. New/unusual IP address
        ip = event.get("ip_address", "")
        if ip and ip not in _trusted_ips.get(user_id, []):
            seen_ips = {e["ip_address"] for e in _login_events.get(user_id, []) if e.get("success")}
            if ip not in seen_ips:
                anomalies.append({
                    "type": "new_ip_address",
                    "severity": "medium",
                    "description": f"Login from a new IP address: {ip}",
                    "ip_address": ip,
                    "timestamp": event.get("timestamp"),
                })

        # 3. Unusual login time
        try:
            ts = datetime.fromisoformat(event["timestamp"])
            hour = ts.hour
            if self.UNUSUAL_TIME_START <= hour < self.UNUSUAL_TIME_END:
                anomalies.append({
                    "type": "unusual_login_time",
                    "severity": "low",
                    "description": f"Login at unusual hour: {ts.strftime(%H:%M