# Login Anomaly Detection & Suspicious Activity Alerts

## Overview

FinMind now tracks login activity and automatically detects suspicious patterns, alerting users when anomalies are found.

## Features

### Login History Tracking
Every login attempt (successful or failed) is recorded with:
- IP address (from `X-Forwarded-For` header or direct connection)
- User agent string (device/browser fingerprint)
- Timestamp
- Success/failure status
- Detected anomaly flags

### Anomaly Detection
The system checks for four types of anomalies on each successful login:

| Anomaly | Flag | Description |
|---------|------|-------------|
| New IP Address | `new_ip` | Login from an IP not previously seen for this user |
| New Device | `new_device` | Login from a user agent not previously seen |
| Unusual Time | `unusual_time` | Login during UTC 01:00–05:00 |
| Brute Force | `multiple_failed_attempts` | 5+ failed login attempts within 30 minutes |

### Alerting
When anomalies are detected:
1. **In-app alerts** are created in the `security_alerts` table
2. **Email notifications** are sent (if SMTP is configured)
3. **Login response** includes `security_warnings` array

Duplicate alerts of the same type are suppressed within a 1-hour window.

## API Endpoints

All endpoints require JWT authentication (Bearer token).

### `GET /auth/login-history`
Returns paginated login history for the authenticated user.

**Query Parameters:**
- `page` (int, default: 1)
- `per_page` (int, default: 20, max: 100)

**Response:**
```json
{
  "total": 42,
  "page": 1,
  "per_page": 20,
  "items": [
    {
      "id": 1,
      "ip_address": "192.168.1.1",
      "user_agent": "Mozilla/5.0 ...",
      "success": true,
      "anomaly_flags": ["new_ip"],
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### `GET /auth/security-alerts`
Returns security alerts (up to 50 most recent).

**Response:**
```json
{
  "items": [
    {
      "id": 1,
      "alert_type": "new_ip",
      "message": "Login from a new IP address: 203.0.113.42",
      "acknowledged": false,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### `POST /auth/security-alerts/<id>/acknowledge`
Mark a security alert as acknowledged. Returns 404 if the alert doesn't belong to the authenticated user.

### `POST /auth/login` (updated)
The login response now includes `security_warnings` when anomalies are detected:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "security_warnings": ["new_ip", "new_device"]
}
```

## Database Tables

### `login_history`
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| user_id | INT | Foreign key to users |
| ip_address | VARCHAR(45) | Client IP (supports IPv6) |
| user_agent | VARCHAR(500) | Browser/client identifier |
| success | BOOLEAN | Whether login succeeded |
| anomaly_flags | TEXT | JSON array of detected anomaly flags |
| created_at | TIMESTAMP | When the login occurred |

### `security_alerts`
| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| user_id | INT | Foreign key to users |
| alert_type | VARCHAR(50) | Anomaly type identifier |
| message | VARCHAR(500) | Human-readable alert message |
| metadata_json | TEXT | JSON with IP and user agent details |
| acknowledged | BOOLEAN | Whether user dismissed the alert |
| created_at | TIMESTAMP | When the alert was created |

## Configuration

No additional configuration is required. Email alerts use the existing SMTP settings (`SMTP_URL`, `EMAIL_FROM`).

## Thresholds

Default thresholds (configurable in `app/services/login_anomaly.py`):
- **Failed attempt threshold:** 5 attempts
- **Failed attempt window:** 30 minutes
- **Unusual hour range:** UTC 01:00–05:00
- **Alert dedup window:** 1 hour
