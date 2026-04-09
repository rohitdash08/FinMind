from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    unset_jwt_cookies,
    get_jwt,
)
from app.extensions import db, jwt # Assuming jwt extension is configured
from app.models import User
from app.utils.alerts import send_alert_email

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    """Registers a new user."""
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"message": "User with that email already exists"}), 409

    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "User registered successfully", "id": user.id}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticates a user and performs login anomaly detection.
    On successful login, tokens are issued, and last login details are updated.
    If a new IP or User-Agent is detected, a suspicious activity alert is triggered.
    """
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()

    if user and user.check_password(password):
        # Generate tokens
        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)

        # Anomaly detection logic
        current_ip = request.remote_addr
        current_user_agent = request.headers.get("User-Agent")
        current_time = datetime.now(timezone.utc)

        is_suspicious = False
        alert_reason_parts = []

        # Check for new IP address (if a previous one exists)
        if user.last_login_ip and user.last_login_ip != current_ip:
            is_suspicious = True
            alert_reason_parts.append(f"new IP address: {current_ip}")
        
        # Check for new User-Agent (if a previous one exists)
        if user.last_login_user_agent and user.last_login_user_agent != current_user_agent:
            is_suspicious = True
            alert_reason_parts.append(f"new User-Agent: '{current_user_agent}'")

        if is_suspicious:
            # Trigger alert (e.g., send email)
            current_app.logger.warning(
                f"Suspicious login detected for user {user.email}: "
                f"{', '.join(alert_reason_parts)}. Triggering alert."
            )
            send_alert_email(user.email, current_ip, current_user_agent, current_time)

        # Update last login details for the user
        user.last_login_ip = current_ip
        user.last_login_user_agent = current_user_agent
        user.last_login_at = current_time
        db.session.commit()

        return jsonify(access_token=access_token, refresh_token=refresh_token), 200
    else:
        return jsonify({"message": "Invalid credentials"}), 401


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Refreshes an access token using a valid refresh token."""
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity)
    return jsonify(access_token=access_token), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required(refresh=True)
def logout():
    """
    Logs out the user by revoking the refresh token.
    (In a production system, this would typically add the JTI to a blocklist).
    """
    jti = get_jwt()["jti"]
    # Placeholder for refresh token revocation (e.g., adding JTI to a Redis blocklist)
    current_app.logger.info(f"Logout successful for JTI: {jti}")
    response = jsonify({"message": "Logout successful"})
    unset_jwt_cookies(response) # Useful if JWTs are stored in cookies
    return response, 200


@auth_bp.route("/me", methods=["GET", "PATCH"])
@jwt_required()
def me():
    """
    Retrieves or updates current user's profile information.
    GET: Returns current user details.
    PATCH: Updates user's preferred currency.
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"message": "User not found"}), 404

    if request.method == "GET":
        return jsonify(user.to_dict()), 200
    elif request.method == "PATCH":
        data = request.get_json()
        preferred_currency = data.get("preferred_currency")
        if preferred_currency:
            # Basic validation for currency format (e.g., "INR", "USD")
            if not (
                isinstance(preferred_currency, str)
                and len(preferred_currency) == 3
                and preferred_currency.isupper()
            ):
                return (
                    jsonify(
                        {"message": "Invalid currency format. Use uppercase 3-letter code (e.g., USD)."}
                    ),
                    400,
                )
            user.preferred_currency = preferred_currency
            db.session.commit()
            return jsonify(user.to_dict()), 200
        return jsonify({"message": "No valid fields to update"}), 400

