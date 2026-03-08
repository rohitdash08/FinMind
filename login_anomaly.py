import time
from collections import defaultdict
import json

# A simple in-memory store to track login attempts
login_attempts = defaultdict(list)

# Thresholds for detecting unusual behavior
MAX_ATTEMPTS = 5
TIME_WINDOW = 60 * 60  # 1 hour window

# Mock function for sending alerts (could be integrated with email/SMS/notifications)
def send_alert(user_id):
    print(f"ALERT: Suspicious activity detected for user {user_id}")

# Function to track login attempts
def track_login(user_id, ip_address):
    current_time = time.time()
    login_attempts[user_id].append((current_time, ip_address))
    
    # Remove attempts older than the defined time window
    login_attempts[user_id] = [
        (t, ip) for t, ip in login_attempts[user_id] if current_time - t < TIME_WINDOW
    ]

# Function to detect suspicious login activity
def detect_anomalies(user_id):
    attempts = login_attempts.get(user_id, [])
    
    if len(attempts) >= MAX_ATTEMPTS:
        ips = [ip for _, ip in attempts]
        if len(set(ips)) > 1:
            # Multiple logins from different IP addresses detected
            send_alert(user_id)
            return True
    return False

# Example Usage
track_login("user123", "192.168.1.1")
track_login("user123", "192.168.1.2")
track_login("user123", "192.168.1.3")

if detect_anomalies("user123"):
    print("Anomaly detected for user123")