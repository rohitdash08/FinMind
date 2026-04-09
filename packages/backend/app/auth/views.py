from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, unset_jwt_cookies

from app.extensions import db
from app.models import User, LoginAttempt
from app.utils.security import detect_suspicious_login, send_suspicious_activity_email
from datetime import datetime
import pytz

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ... other imports / boilerplate ...

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()

    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent')

    if user and user.check_password(password):
        # Successful login
        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)

        # Anomaly detection
        is_suspicious = detect_suspicious_login(user, ip_address, user_agent)
        if is_suspicious:
            # Trigger alert for suspicious activity
            # Create a temporary LoginAttempt object to pass full context to the email sender
            # before the actual attempt is committed, ensuring the alert has current data.
            temp_login_attempt_for_email = LoginAttempt(
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                timestamp=datetime.now(pytz.utc), # Use current time for the alert
                status='success',
                is_suspicious=True
            )
            send_suspicious_activity_email(user, temp_login_attempt_for_email)

        # Update last login info on the User model
        user.last_login_at = datetime.now(pytz.utc)
        user.last_login_ip = ip_address
        user.last_login_user_agent = user_agent
        db.session.add(user) # Persist user update

        # Record this successful login attempt in the LoginAttempt table
        login_attempt = LoginAttempt(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            status='success',
            is_suspicious=is_suspicious
        )
        db.session.add(login_attempt)
        db.session.commit() # Commit all changes

        return jsonify(
            access_token=access_token, refresh_token=refresh_token
        ), 200
    else:
        # Failed login attempt
        # Record failed login for auditing (if user exists, otherwise it's just a bad email attempt)
        if user: # Only log failures associated with a known user email for security audit
            login_attempt = LoginAttempt(
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                status='failure',
                is_suspicious=False # Failed logins aren't 'suspicious' in terms of account takeover
            )
            db.session.add(login_attempt)
            db.session.commit() # Commit failed login attempt

        return jsonify({"msg": "Bad email or password"}), 401

# ... rest of the file ...