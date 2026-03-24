# Login Anomaly Detection & Security Alerts

This document describes the login anomaly detection and suspicious activity alerts feature in FinMind.

## Overview

The security system provides real-time detection of suspicious login activities and automatically generates alerts when potential security threats are detected. This helps protect user accounts from unauthorized access.

## Features

### 1. Multi-Factor Risk Scoring

The system calculates a risk score (0.0 to 1.0) based on multiple signals:

| Risk Factor | Weight | Description |
|-------------|--------|-------------|
| New IP Address | 0.30 | Login from an IP not previously seen for this user |
| New Device | 0.25 | Login from a device fingerprint not previously seen |
| Unusual Time | 0.15 | Login during unusual hours (1 AM - 5 AM UTC) |
| Recent Failed Attempts | 0.10-0.40 | Multiple failed login attempts in last 15 minutes |
| Rapid Location Change | 0.30 | Login from different IP within 1 hour |

### 2. Brute Force Protection

- **Threshold**: 5 failed attempts within 15 minutes
- **Block Duration**: 30 minutes
- **Storage**: Redis with automatic expiration

### 3. Automatic Alert Generation

Security alerts are automatically created when:
- Risk score >= 0.5 (Medium/High severity)
- Brute force threshold is reached
- Suspicious patterns are detected

### 4. Login Event Tracking

All login events are recorded with:
- User ID
- Event type (success, failed, blocked, etc.)
- IP address
- User agent
- Device fingerprint
- Location metadata
- Risk score and factors

## API Endpoints

### Record Login Event

```http
POST /security/record
Authorization: Bearer <token>
Content-Type: application/json

{
    "event_type": "login_success",
    "ip_address": "192.168.1.1",
    "device_fingerprint": "abc123",
    "location_country": "United States",
    "location_city": "New York"
}
```

Response:
```json
{
    "message": "event recorded",
    "event": {
        "id": 1,
        "event_type": "login_success",
        "ip_address": "192.168.1.1",
        "risk_score": 0.3,
        "risk_factors": ["new_ip_address"]
    },
    "risk_score": 0.3,
    "risk_factors": ["new_ip_address"]
}
```

### Get Login History

```http
GET /security/history?event_type=login_success&limit=50&offset=0
Authorization: Bearer <token>
```

Response:
```json
{
    "events": [...],
    "count": 10,
    "limit": 50,
    "offset": 0
}
```

### Get Security Alerts

```http
GET /security/alerts?status=active&severity=high
Authorization: Bearer <token>
```

Response:
```json
{
    "alerts": [
        {
            "id": 1,
            "alert_type": "suspicious_login",
            "severity": "high",
            "status": "active",
            "title": "Suspicious Login Detected",
            "description": "Login from new IP and device",
            "ip_address": "192.168.1.1",
            "created_at": "2026-03-24T10:00:00Z"
        }
    ],
    "count": 1
}
```

### Acknowledge Alert

```http
POST /security/alerts/1/acknowledge
Authorization: Bearer <token>
```

Response:
```json
{
    "message": "alert acknowledged",
    "alert": {
        "id": 1,
        "status": "acknowledged",
        "acknowledged_at": "2026-03-24T11:00:00Z"
    }
}
```

### Acknowledge All Alerts

```http
POST /security/alerts/acknowledge-all
Authorization: Bearer <token>
```

Response:
```json
{
    "message": "all alerts acknowledged",
    "count": 3
}
```

### Get Security Statistics

```http
GET /security/stats?days=30
Authorization: Bearer <token>
```

Response:
```json
{
    "period_days": 30,
    "total_logins": 45,
    "failed_logins": 3,
    "unique_ips": 2,
    "unique_devices": 2,
    "active_alerts": 1,
    "total_alerts": 5,
    "high_risk_logins": 2,
    "login_success_rate": 93.8
}
```

### Analyze Login Risk

```http
POST /security/analyze
Authorization: Bearer <token>
Content-Type: application/json

{
    "ip_address": "192.168.1.1",
    "device_fingerprint": "abc123"
}
```

Response:
```json
{
    "ip_address": "192.168.1.1",
    "device_fingerprint": "abc123",
    "risk_score": 0.55,
    "risk_factors": ["new_ip_address", "new_device"],
    "recommendation": "review"
}
```

### Check IP Block Status

```http
GET /security/check-ip
Authorization: Bearer <token>
```

Response:
```json
{
    "ip_address": "192.168.1.1",
    "blocked": false
}
```

## Database Schema

### login_events Table

```sql
CREATE TABLE login_events (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(30) NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    device_fingerprint VARCHAR(128),
    location_country VARCHAR(100),
    location_city VARCHAR(100),
    risk_score NUMERIC(3,2) DEFAULT 0.0,
    risk_factors TEXT,  -- JSON array
    created_at TIMESTAMP DEFAULT NOW()
);
```

### security_alerts Table

```sql
CREATE TABLE security_alerts (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(20) DEFAULT 'active',
    title VARCHAR(200) NOT NULL,
    description TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    login_event_id INT REFERENCES login_events(id),
    acknowledged_at TIMESTAMP,
    acknowledged_by INT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Alert Types

| Alert Type | Description | Default Severity |
|------------|-------------|------------------|
| `suspicious_login` | Login with elevated risk score | medium/high |
| `brute_force_detected` | Multiple failed login attempts | high |
| `new_device_login` | First login from new device | low |
| `new_location_login` | Login from new geographic location | medium |

## Alert Severities

| Severity | Description |
|----------|-------------|
| `low` | Minor anomaly, informational |
| `medium` | Moderate concern, review recommended |
| `high` | Significant concern, immediate review |
| `critical` | Critical security issue, urgent action |

## Alert Statuses

| Status | Description |
|--------|-------------|
| `active` | New alert, requires attention |
| `acknowledged` | User has seen the alert |
| `resolved` | Issue has been resolved |

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BRUTE_FORCE_THRESHOLD` | Failed attempts before block | 5 |
| `BRUTE_FORCE_WINDOW_MINUTES` | Time window for counting attempts | 15 |
| `BRUTE_FORCE_BLOCK_MINUTES` | Block duration after threshold | 30 |

### Redis Keys

| Key Pattern | Purpose | TTL |
|-------------|---------|-----|
| `security:brute_force:{ip}` | Failed attempt counter | 15 min |
| `security:brute_force:{ip}:blocked` | Block flag | 30 min |
| `security:user_ips:{user_id}` | Known IPs for user | 30 days |
| `security:user_devices:{user_id}` | Known devices for user | 30 days |

## Integration with Auth Flow

The login anomaly detection is integrated into the `/auth/login` endpoint:

1. Check if IP is blocked due to brute force
2. Process login credentials
3. Calculate risk score if successful
4. Record login event
5. Generate alert if risk threshold exceeded
6. Return tokens with security information

### Login Response with Security Info

```json
{
    "access_token": "...",
    "refresh_token": "...",
    "security_alert": {
        "type": "suspicious_login",
        "severity": "medium",
        "message": "Suspicious Login Detected"
    },
    "security_notice": {
        "risk_score": 0.55,
        "message": "Login from new device or location detected"
    }
}
```

## Testing

Run the security tests:

```bash
# Using the test script
./scripts/test-backend.ps1 tests/test_security.py

# Or directly with pytest
cd packages/backend
pytest tests/test_security.py -v
```

## Best Practices

### For Users

1. Acknowledge security alerts promptly
2. Review login history regularly
3. Report unrecognized login activities
4. Enable additional security measures when available

### For Developers

1. Always check risk scores before allowing sensitive operations
2. Log security events for audit purposes
3. Use Redis for fast brute force detection
4. Keep risk thresholds configurable for different environments

## Future Enhancements

- [ ] Email/SMS notifications for security alerts
- [ ] Machine learning-based risk scoring
- [ ] Geographic location using GeoIP database
- [ ] Two-factor authentication integration
- [ ] Session management and remote logout

---

# Device Trust Management

Users can view and manage their trusted devices for enhanced security.

## Features

- **List Trusted Devices**: View all devices marked as trusted
- **Trust Device**: Mark current or specified device as trusted
- **Remove Trust**: Revoke trust from devices
- **Device Status**: Check if current device is trusted

## API Endpoints

### List Trusted Devices

```http
GET /security/devices
Authorization: Bearer <token>
```

Response:
```json
{
    "devices": [
        {
            "id": 1,
            "device_name": "My Laptop",
            "user_agent": "Mozilla/5.0...",
            "ip_address": "192.168.1.1",
            "last_used_at": "2026-03-24T10:00:00Z",
            "trusted_at": "2026-03-20T08:00:00Z",
            "is_active": true
        }
    ],
    "count": 1
}
```

### Trust Device

```http
POST /security/devices/trust
Authorization: Bearer <token>
Content-Type: application/json

{
    "device_name": "My Laptop"
}
```

Response:
```json
{
    "message": "device trusted",
    "device": {
        "id": 1,
        "device_name": "My Laptop",
        ...
    }
}
```

### Remove Device Trust

```http
DELETE /security/devices/1
Authorization: Bearer <token>
```

Response:
```json
{
    "message": "device trust removed"
}
```

### Check Device Status

```http
GET /security/devices/status
Authorization: Bearer <token>
```

Response:
```json
{
    "trusted": true,
    "device_fingerprint": "abc123..."
}
```

### Update Device Name

```http
PATCH /security/devices/1
Authorization: Bearer <token>
Content-Type: application/json

{
    "device_name": "Work Laptop"
}
```

## Database Schema

### trusted_devices Table

```sql
CREATE TABLE trusted_devices (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_fingerprint VARCHAR(128) NOT NULL,
    device_name VARCHAR(100),
    user_agent VARCHAR(500),
    ip_address VARCHAR(45),
    last_used_at TIMESTAMP DEFAULT NOW(),
    trusted_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Integration with Login

When a user logs in, the system checks if the device is trusted:

1. If trusted: Lower risk score, smoother login
2. If not trusted: Standard risk assessment

## Testing

Run the device trust tests:

```bash
cd packages/backend
pytest tests/test_device_trust.py -v
```