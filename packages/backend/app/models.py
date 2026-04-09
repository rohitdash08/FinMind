from datetime import datetime
from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    """
    Represents a user in the system.
    Includes fields for authentication, preferences, and login anomaly detection.
    """
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    preferred_currency = db.Column(db.String(3), default="INR")

    # Fields for login anomaly detection
    last_login_ip = db.Column(db.String(45), nullable=True) # Supports IPv4 and IPv6
    last_login_user_agent = db.Column(db.String(512), nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<User {self.email}>"

    def set_password(self, password):
        """Hashes the password and stores it."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Checks if the provided password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Returns a dictionary representation of the user, excluding sensitive data."""
        return {
            "id": self.id,
            "email": self.email,
            "preferred_currency": self.preferred_currency,
        }

