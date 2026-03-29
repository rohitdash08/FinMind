"""Login Anomaly Detection Service.

Detects and alerts on suspicious login behavior:
- New device detection
- Anomaly IP/geo detection  
- Anomaly login time
- Multiple failed attempts
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, asdict

from sqlalchemy import func, and_
from ..extensions import db
from ..models import (
    LoginAttempt,
    UserDevice,
    LoginAnomaly,
    LoginAnomalyType,
    User,
)

logger = logging.getLogger("finmind.login_anomaly")


@dataclass
class AnomalyResult:
    """Result of anomaly detection."""
    is_anomaly: bool
    anomaly_type: Optional[LoginAnomalyType] = None
    severity: str = "low"  # low, medium, high
    details: dict = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


@dataclass
class LoginContext:
    """Context for a login attempt."""
    user_id: Optional[int]
    email: str
    ip_address: str
    user_agent: Optional[str] = None
    device_fingerprint: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None


class LoginAnomalyDetector:
    """Detects anomalous login behavior."""
    
    # Thresholds for detection
    MAX_FAILED_ATTEMPTS = 5  # Max failed attempts before alert
    FAILED_ATTEMPTS_WINDOW_HOURS = 1  # Time window for counting failures
    UNUSUAL_HOUR_START = 0  # Midnight
    UNUSUAL_HOUR_END = 5  # 5 AM
    MIN_LOGINS_FOR_PATTERN = 5  # Min logins before detecting time patterns
    
    def __init__(self, app=None):
        self.app = app
        
    def detect_device_fingerprint(self, user_agent: str, ip_address: str) -> str:
        """Generate a device fingerprint from user agent and IP."""
        if not user_agent:
            user_agent = "unknown"
        data = f"{user_agent}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    def record_login_attempt(
        self,
        context: LoginContext,
        success: bool,
        failure_reason: Optional[str] = None
    ) -> LoginAttempt:
        """Record a login attempt and return the created record."""
        attempt = LoginAttempt(
            user_id=context.user_id,
            email=context.email,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            device_fingerprint=context.device_fingerprint,
            success=success,
            failure_reason=failure_reason,
            country=context.country,
            city=context.city,
        )
        db.session.add(attempt)
        db.session.flush()  # Get the ID without committing
        return attempt
    
    def check_new_device(self, context: LoginContext) -> AnomalyResult:
        """Check if this is a new/unknown device for the user."""
        if not context.user_id:
            return AnomalyResult(is_anomaly=False)
        
        if not context.device_fingerprint:
            return AnomalyResult(is_anomaly=False)
        
        existing = db.session.query(UserDevice).filter(
            and_(
                UserDevice.user_id == context.user_id,
                UserDevice.device_fingerprint == context.device_fingerprint,
                UserDevice.is_revoked == False
            )
        ).first()
        
        if existing:
            # Update last seen
            existing.last_seen = datetime.utcnow()
            existing.ip_address = context.ip_address
            return AnomalyResult(is_anomaly=False)
        
        # New device detected
        return AnomalyResult(
            is_anomaly=True,
            anomaly_type=LoginAnomalyType.NEW_DEVICE,
            severity="medium",
            details={
                "device_fingerprint": context.device_fingerprint,
                "user_agent": context.user_agent,
                "ip_address": context.ip_address,
            }
        )
    
    def check_new_location(self, context: LoginContext) -> AnomalyResult:
        """Check if this is a new geographic location for the user."""
        if not context.user_id:
            return AnomalyResult(is_anomaly=False)
        
        if not context.country:
            return AnomalyResult(is_anomaly=False)
        
        # Check if we've seen this country before
        previous_locations = db.session.query(
            LoginAttempt.country, LoginAttempt.city
        ).filter(
            and_(
                LoginAttempt.user_id == context.user_id,
                LoginAttempt.success == True,
                LoginAttempt.country != None
            )
        ).distinct().all()
        
        if not previous_locations:
            # First login, no baseline
            return AnomalyResult(is_anomaly=False)
        
        known_countries = {loc[0] for loc in previous_locations}
        
        if context.country not in known_countries:
            return AnomalyResult(
                is_anomaly=True,
                anomaly_type=LoginAnomalyType.NEW_LOCATION,
                severity="high",
                details={
                    "new_country": context.country,
                    "new_city": context.city,
                    "known_countries": list(known_countries),
                }
            )
        
        return AnomalyResult(is_anomaly=False)
    
    def check_unusual_time(self, context: LoginContext) -> AnomalyResult:
        """Check if login time is unusual for this user."""
        if not context.user_id:
            return AnomalyResult(is_anomaly=False)
        
        # Get user's typical login hours
        successful_logins = db.session.query(
            func.extract('hour', LoginAttempt.created_at).label('hour')
        ).filter(
            and_(
                LoginAttempt.user_id == context.user_id,
                LoginAttempt.success == True
            )
        ).all()
        
        if len(successful_logins) < self.MIN_LOGINS_FOR_PATTERN:
            # Not enough data to establish pattern
            return AnomalyResult(is_anomaly=False)
        
        # Calculate typical login hours (hours with at least 1 login)
        typical_hours = {int(login.hour) for login in successful_logins}
        
        current_hour = datetime.utcnow().hour
        
        # Check if current hour is in unusual range AND not in typical hours
        if (self.UNUSUAL_HOUR_START <= current_hour <= self.UNUSUAL_HOUR_END
            and current_hour not in typical_hours):
            return AnomalyResult(
                is_anomaly=True,
                anomaly_type=LoginAnomalyType.UNUSUAL_TIME,
                severity="low",
                details={
                    "current_hour": current_hour,
                    "typical_hours": sorted(list(typical_hours)),
                }
            )
        
        return AnomalyResult(is_anomaly=False)
    
    def check_multiple_failures(self, email: str) -> AnomalyResult:
        """Check for multiple failed login attempts."""
        window_start = datetime.utcnow() - timedelta(hours=self.FAILED_ATTEMPTS_WINDOW_HOURS)
        
        failed_count = db.session.query(func.count(LoginAttempt.id)).filter(
            and_(
                LoginAttempt.email == email,
                LoginAttempt.success == False,
                LoginAttempt.created_at >= window_start
            )
        ).scalar()
        
        if failed_count >= self.MAX_FAILED_ATTEMPTS:
            return AnomalyResult(
                is_anomaly=True,
                anomaly_type=LoginAnomalyType.MULTIPLE_FAILURES,
                severity="high",
                details={
                    "failed_count": failed_count,
                    "window_hours": self.FAILED_ATTEMPTS_WINDOW_HOURS,
                }
            )
        
        return AnomalyResult(is_anomaly=False)
    
    # Known suspicious IP patterns
    SUSPICIOUS_IP_PATTERNS = [
        "10.",       # Private IP (should not appear in production)
        "192.168.",  # Private IP
        "127.",      # Localhost (suspicious for remote login)
        "0.0.0.0",   # Invalid
    ]
    
    # Known VPN/Proxy/Tor exit node indicators (can be expanded)
    TOR_EXIT_NODE_INDICATORS = []  # Would be populated from external source
    
    def check_suspicious_ip(self, context: LoginContext) -> AnomalyResult:
        """
        Check if the IP address is suspicious.
        
        Detects:
        - Private/internal IPs (should not appear in production login)
        - Known Tor exit nodes (if data available)
        - VPN/Proxy indicators (if data available)
        - IP from high-risk country (placeholder for Geo-IP risk scoring)
        """
        if not context.ip_address:
            return AnomalyResult(is_anomaly=False)
        
        ip = context.ip_address
        
        # Check for private/internal IPs (suspicious for production)
        for pattern in self.SUSPICIOUS_IP_PATTERNS:
            if ip.startswith(pattern):
                return AnomalyResult(
                    is_anomaly=True,
                    anomaly_type=LoginAnomalyType.SUSPICIOUS_IP,
                    severity="high",
                    details={
                        "ip_address": ip,
                        "reason": "private_or_internal_ip",
                        "pattern_matched": pattern,
                    }
                )
        
        # Check for high-risk countries (if geo data available)
        HIGH_RISK_COUNTRIES = []  # Placeholder: would be from threat intelligence
        if context.country and context.country in HIGH_RISK_COUNTRIES:
            return AnomalyResult(
                is_anomaly=True,
                anomaly_type=LoginAnomalyType.SUSPICIOUS_IP,
                severity="medium",
                details={
                    "ip_address": ip,
                    "country": context.country,
                    "reason": "high_risk_country",
                }
            )
        
        return AnomalyResult(is_anomaly=False)
    
    def run_all_checks(
        self,
        context: LoginContext,
        is_success: bool
    ) -> list[AnomalyResult]:
        """Run all anomaly checks and return list of detected anomalies."""
        anomalies = []
        
        # Check for multiple failures (for both success and failure)
        failure_anomaly = self.check_multiple_failures(context.email)
        if failure_anomaly.is_anomaly:
            anomalies.append(failure_anomaly)
        
        # Only run device/location/time checks on successful login
        if is_success and context.user_id:
            device_anomaly = self.check_new_device(context)
            if device_anomaly.is_anomaly:
                anomalies.append(device_anomaly)
            
            location_anomaly = self.check_new_location(context)
            if location_anomaly.is_anomaly:
                anomalies.append(location_anomaly)
            
            time_anomaly = self.check_unusual_time(context)
            if time_anomaly.is_anomaly:
                anomalies.append(time_anomaly)
            
            # Check for suspicious IP (for both success and failure)
            ip_anomaly = self.check_suspicious_ip(context)
            if ip_anomaly.is_anomaly:
                anomalies.append(ip_anomaly)
        
        return anomalies
    
    def register_device(
        self,
        context: LoginContext,
        device_name: Optional[str] = None
    ) -> UserDevice:
        """Register a new device for a user."""
        if not context.user_id:
            raise ValueError("user_id required to register device")
        
        device = UserDevice(
            user_id=context.user_id,
            device_fingerprint=context.device_fingerprint or self.detect_device_fingerprint(
                context.user_agent or "", context.ip_address
            ),
            device_name=device_name,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            country=context.country,
            city=context.city,
        )
        db.session.add(device)
        return device
    
    def record_anomaly(
        self,
        user_id: int,
        login_attempt_id: Optional[int],
        anomaly_type: LoginAnomalyType,
        severity: str,
        details: dict
    ) -> LoginAnomaly:
        """Record a detected anomaly."""
        anomaly = LoginAnomaly(
            user_id=user_id,
            login_attempt_id=login_attempt_id,
            anomaly_type=anomaly_type,
            severity=severity,
            details=json.dumps(details) if details else None,
        )
        db.session.add(anomaly)
        return anomaly
    
    def process_login(
        self,
        context: LoginContext,
        success: bool,
        failure_reason: Optional[str] = None
    ) -> tuple[LoginAttempt, list[LoginAnomaly]]:
        """
        Process a login attempt: record it, detect anomalies, and create alerts.
        Returns the LoginAttempt and any detected anomalies.
        """
        # Generate device fingerprint if not provided
        if not context.device_fingerprint and context.user_agent:
            context.device_fingerprint = self.detect_device_fingerprint(
                context.user_agent, context.ip_address
            )
        
        # Record the attempt
        attempt = self.record_login_attempt(context, success, failure_reason)
        
        # Detect anomalies
        anomalies = self.run_all_checks(context, success)
        
        # Record anomalies
        recorded_anomalies = []
        for anomaly in anomalies:
            if context.user_id:
                recorded = self.record_anomaly(
                    user_id=context.user_id,
                    login_attempt_id=attempt.id,
                    anomaly_type=anomaly.anomaly_type,
                    severity=anomaly.severity,
                    details=anomaly.details,
                )
                recorded_anomalies.append(recorded)
                logger.warning(
                    "Login anomaly detected: user_id=%s type=%s severity=%s",
                    context.user_id,
                    anomaly.anomaly_type.value,
                    anomaly.severity
                )
        
        # On successful login, ensure device is registered
        if success and context.user_id:
            existing_device = db.session.query(UserDevice).filter(
                and_(
                    UserDevice.user_id == context.user_id,
                    UserDevice.device_fingerprint == context.device_fingerprint
                )
            ).first()
            
            if existing_device:
                existing_device.last_seen = datetime.utcnow()
                existing_device.ip_address = context.ip_address
            else:
                self.register_device(context)
        
        return attempt, recorded_anomalies


# Global detector instance
detector = LoginAnomalyDetector()


def get_client_ip(request) -> str:
    """Extract client IP from request, handling proxies."""
    # Check X-Forwarded-For header (behind proxy)
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    
    # Check X-Real-IP header (nginx)
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    
    # Fall back to direct connection
    return request.remote_addr or '0.0.0.0'


def get_geo_from_ip(ip_address: str) -> dict:
    """
    Get geographic information from IP address.
    
    Uses ip-api.com (free tier, no API key required, 45 requests/min limit).
    For production, consider using MaxMind GeoIP2 or similar paid service.
    
    Returns: {"country": str, "city": str} or empty dict on failure.
    """
    if not ip_address:
        return {}
    
    # Skip private/internal IPs
    PRIVATE_IP_PREFIXES = ("10.", "192.168.", "172.16.", "172.17.", "172.18.", 
                           "172.19.", "172.20.", "172.21.", "172.22.", "172.23.",
                           "172.24.", "172.25.", "172.26.", "172.27.", "172.28.",
                           "172.29.", "172.30.", "172.31.", "127.", "169.254.", "::1")
    if ip_address.startswith(PRIVATE_IP_PREFIXES):
        return {"country": None, "city": None}
    
    try:
        import requests
        response = requests.get(
            f"http://ip-api.com/json/{ip_address}",
            timeout=2.0,
            params={"fields": "status,countryCode,city"}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return {
                    "country": data.get("countryCode"),
                    "city": data.get("city"),
                }
    except Exception as e:
        logger.debug(f"Geo-IP lookup failed for {ip_address}: {e}")
    
    return {}


def get_login_context(request, user_id: Optional[int], email: str) -> LoginContext:
    """Build LoginContext from Flask request."""
    user_agent = request.headers.get('User-Agent', '')[:500]  # Truncate to fit column
    ip_address = get_client_ip(request)
    
    # Generate device fingerprint
    device_fingerprint = detector.detect_device_fingerprint(user_agent, ip_address)
    
    # Get geo information from IP
    geo = get_geo_from_ip(ip_address)
    
    return LoginContext(
        user_id=user_id,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        device_fingerprint=device_fingerprint,
        country=geo.get("country"),
        city=geo.get("city"),
    )
