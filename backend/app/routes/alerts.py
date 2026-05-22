from flask import Blueprint, jsonify
from app.models import AuditLog, db
from app.extensions import mail
from flask_mail import Message

alerts = Blueprint('alerts', __name__)

@alerts.route('/suspicious-activity', methods=['GET'])
def suspicious_activity_alerts():
    suspicious_logs = AuditLog.query.filter_by(activity='Suspicious login attempt').all()
    if not suspicious_logs:
        return jsonify({"msg": "No suspicious activity detected"}), 200

    msg = Message("Suspicious Activity Alert", sender="noreply@finmind.com", recipients=["admin@finmind.com"])
    msg.body = "Suspicious login attempts detected:\n\n" + "\n".join([f"User ID: {log.user_id}, Timestamp: {log.timestamp}" for log in suspicious_logs])
    mail.send(msg)

    return jsonify({"msg": "Suspicious activity alerts sent"}), 200