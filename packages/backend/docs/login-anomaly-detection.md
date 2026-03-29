# Login Anomaly Detection

FinMind includes a login anomaly detection system to help protect user accounts from unauthorized access.

## Features

### Detection Types

1. **New Device Detection**
   - Tracks known devices using browser fingerprinting
   - Alerts when a login occurs from an unrecognized device
   - Severity: Medium

2. **New Location Detection**
   - Tracks geographic locations (country) of successful logins
   - Alerts when a login occurs from a new country
   - Severity: High

3. **Unusual Time Detection**
   - Learns typical login hours for each user
   - Alerts on logins during unusual hours (midnight to 5 AM UTC) if not typical
   - Severity: Low

4. **Multiple Failed Attempts**
   - Monitors failed login attempts per email address
   - Alerts after 5+ failed attempts within 1 hour
   - Severity: High

## API Endpoints

### Security Endpoints

All endpoints require authentication via JWT.

#### List Devices
```
GET /security/devices
```
Returns list of registered devices for the current user.

**Response:**
```json
[
  {
    "id": 1,
    "device_name": "My Laptop",
    "ip_address": "192.168.1.1",
    "user_agent": "Mozilla/5.0...",
    "country": "US",
    "city": "New York",
    "first_seen": "2024-01-15T10:30:00Z",
    "last_seen": "2024-01-20T08:15:00Z",
    "is_trusted": true,
    "is_revoked": false
  }
]
```

#### Update Device
```
PATCH /security/devices/{device_id}
```
Update device settings (name, trusted status, or revoke).

**Request Body:**
```json
{
  "device_name": "My Work Laptop",
  "is_trusted": true,
  "is_revoked": false
}
```

#### Revoke Device
```
DELETE /security/devices/{device_id}
```
Revoke a device's access.

#### Login History
```
GET /security/login-history?limit=20
```
Get recent login attempts for the current user.

**Response:**
```json
[
  {
    "id": 1,
    "ip_address": "192.168.1.1",
    "user_agent": "Mozilla/5.0...",
    "success": true,
    "country": "US",
    "city": "New York",
    "created_at": "2024-01-20T08:15:00Z"
  }
]
```

#### List Security Alerts
```
GET /security/alerts?limit=20&unacknowledged=true
```
Get security alerts for the current user.

**Response:**
```json
[
  {
    "id": 1,
    "anomaly_type": "new_device",
    "severity": "medium",
    "details": {
      "device_fingerprint": "abc123...",
      "ip_address": "10.0.0.1"
    },
    "acknowledged": false,
    "created_at": "2024-01-20T08:15:00Z"
  }
]
```

#### Acknowledge Alert
```
POST /security/alerts/{alert_id}/acknowledge
```
Mark an alert as acknowledged.

#### Acknowledge All Alerts
```
POST /security/alerts/acknowledge-all
```
Mark all unacknowledged alerts as acknowledged.

### Login Response

When anomalies are detected during login, the response includes a `security_alerts` field:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "security_alerts": [
    {
      "type": "new_device",
      "severity": "medium"
    }
  ]
}
```

## Database Models

### LoginAttempt
Tracks all login attempts (successful and failed).

| Field | Type | Description |
|-------|------|-------------|
| user_id | Integer | User ID (null for unknown email) |
| email | String | Email used for login |
| ip_address | String | Client IP address |
| user_agent | String | Browser user agent |
| device_fingerprint | String | Device identifier |
| success | Boolean | Whether login succeeded |
| failure_reason | String | Reason for failure |
| country | String | Country code (2-letter) |
| city | String | City name |
| created_at | DateTime | Timestamp |

### UserDevice
Registered devices for each user.

| Field | Type | Description |
|-------|------|-------------|
| user_id | Integer | User ID |
| device_fingerprint | String | Unique device identifier |
| device_name | String | User-assigned name |
| ip_address | String | Last IP address |
| user_agent | String | Browser user agent |
| country | String | Country code |
| city | String | City name |
| first_seen | DateTime | First login timestamp |
| last_seen | DateTime | Most recent login |
| is_trusted | Boolean | User-marked as trusted |
| is_revoked | Boolean | Device access revoked |

### LoginAnomaly
Detected anomalies.

| Field | Type | Description |
|-------|------|-------------|
| user_id | Integer | User ID |
| login_attempt_id | Integer | Related login attempt |
| anomaly_type | Enum | Type of anomaly |
| severity | String | low/medium/high |
| details | JSON | Additional details |
| acknowledged | Boolean | User acknowledged |
| created_at | DateTime | Detection timestamp |

## Configuration

Thresholds can be configured in `LoginAnomalyDetector`:

```python
class LoginAnomalyDetector:
    MAX_FAILED_ATTEMPTS = 5  # Max failures before alert
    FAILED_ATTEMPTS_WINDOW_HOURS = 1  # Time window for failures
    UNUSUAL_HOUR_START = 0  # Midnight
    UNUSUAL_HOUR_END = 5  # 5 AM
    MIN_LOGINS_FOR_PATTERN = 5  # Min logins for time pattern
```

## Future Enhancements

- GeoIP integration for accurate location detection
- Email/SMS notifications for high-severity alerts
- Device verification via email code
- Rate limiting based on anomaly score
- Machine learning for improved pattern detection
