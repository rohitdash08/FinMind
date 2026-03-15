# Login Anomaly Detection & Suspicious Activity Alerts

## Overview

Real-time login anomaly detection with risk scoring, automated security alerts,
and comprehensive login history tracking.

## Features

| Feature | Description |
|---------|-------------|
| **Risk scoring** | 0.0-1.0 risk score based on multiple anomaly signals |
| **Anomaly signals** | New IP, new device, unusual time, rapid attempts, failed streaks |
| **Auto alerts** | Security alerts generated for suspicious logins |
| **Alert management** | Acknowledge individual or all alerts |
| **Login history** | Filterable event log with device/location metadata |
| **Statistics** | Login counts, unique IPs/devices, risk distribution |

## Risk Signals

| Signal | Weight | Trigger |
|--------|--------|---------|
| `new_ip` | 0.30 | IP address not seen before |
| `new_device` | 0.25 | Browser/OS combination not seen before |
| `unusual_time` | 0.15 | Login hour >8h from average |
| `rapid_attempts` | 0.40 | 5+ attempts in 10 minutes |
| `new_country` | 0.35 | Country code not seen before |
| `failed_streak` | 0.50 | 3+ consecutive failed logins |

- **Suspicious threshold**: risk_score >= 0.5
- Risk score capped at 1.0

## API Endpoints

Base path: `/security`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/security/record` | Record login event with anomaly check |
| GET | `/security/history` | Get login event history |
| GET | `/security/alerts` | Get security alerts |
| POST | `/security/alerts/:id/acknowledge` | Acknowledge alert |
| POST | `/security/alerts/acknowledge-all` | Acknowledge all |
| GET | `/security/stats` | Login statistics |

### POST /security/record

```json
{
  "event_type": "login",     // login, failed_login, logout
  "session_id": "abc123"     // optional
}
```

### GET /security/history

Query params: `?limit=50&event_type=login&suspicious=true`

### GET /security/stats

Query params: `?days=30`

## Database

### login_events table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| user_id | INTEGER | FK → users.id |
| event_type | VARCHAR(20) | login, failed_login, logout |
| ip_address | VARCHAR(45) | Client IP |
| user_agent | VARCHAR(512) | Full UA string |
| device_type | VARCHAR(20) | desktop, mobile, tablet |
| browser | VARCHAR(64) | Detected browser |
| os | VARCHAR(64) | Detected OS |
| is_suspicious | BOOLEAN | Flagged as suspicious |
| risk_score | REAL | 0.0-1.0 risk score |
| anomaly_reasons | TEXT | JSON array of triggered signals |

### security_alerts table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| user_id | INTEGER | FK → users.id |
| alert_type | VARCHAR(50) | new_ip_login, new_device, etc. |
| severity | VARCHAR(20) | low, medium, high, critical |
| title | VARCHAR(256) | Alert title |
| description | TEXT | Detailed description |
| metadata | TEXT | JSON with alert-specific data |
| acknowledged | BOOLEAN | Whether user acknowledged |

## Testing

37 tests covering:
- User-Agent parsing
- Anomaly detection (new IP, new device, rapid attempts, failed streaks)
- Risk score calculation and thresholds
- Login event recording with alert generation
- Login history with filters
- Security alert lifecycle (create, acknowledge, bulk acknowledge)
- Login statistics
- All route endpoints
