# Login Anomaly Detection and Alerts

## Overview

This module provides functionality for detecting unusual login behavior based on user login patterns. It tracks login attempts and triggers alerts when suspicious activity is detected, such as multiple login attempts from different IP addresses within a short time frame.

## Key Features

- Detects login attempts from multiple IP addresses within a short time window.
- Sends alerts if suspicious behavior is detected (via `send_alert` function).
- Configurable thresholds for max login attempts and time window.
  
## Usage

```python
from login_anomaly import track_login, detect_anomalies

# Track a login attempt
track_login(user_id="user123", ip_address="192.168.1.1")

# Detect if there is any anomaly for the user
detect_anomalies(user_id="user123")
```

## Testing

Tests for the login anomaly detection are provided in `test_login_anomaly.py`, using Python's `unittest` framework.

Run tests with:

```bash
python -m unittest test_login_anomaly.py
```

## Configuration

- `MAX_ATTEMPTS`: The maximum allowed login attempts within the defined time window (default: 5).
- `TIME_WINDOW`: The time window (in seconds) to track login attempts (default: 1 hour).
