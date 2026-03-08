import unittest
from login_anomaly import track_login, detect_anomalies, send_alert

class TestLoginAnomaly(unittest.TestCase):

    def test_multiple_ips(self):
        # Simulating multiple logins from different IPs
        track_login("user123", "192.168.1.1")
        track_login("user123", "192.168.1.2")
        track_login("user123", "192.168.1.3")
        
        # Detect anomaly and verify alert trigger
        with self.assertLogs() as log:
            anomaly_detected = detect_anomalies("user123")
            self.assertTrue(anomaly_detected)
            self.assertIn("ALERT", log.output[0])

    def test_single_ip(self):
        # Simulating logins from the same IP
        track_login("user123", "192.168.1.1")
        track_login("user123", "192.168.1.1")
        
        # Should not detect anomaly
        anomaly_detected = detect_anomalies("user123")
        self.assertFalse(anomaly_detected)

if __name__ == "__main__":
    unittest.main()