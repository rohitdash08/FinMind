class LoginEvent(db.Model):
    __tablename__ = 'login_events'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.String(500))
    location = db.Column(db.String(255))
    success = db.Column(db.Boolean, default=False, nullable=False)
    failure_reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref='login_events')


class SuspiciousActivityAlert(db.Model):
    __tablename__ = 'suspicious_activity_alerts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    alert_type = db.Column(db.String(50), nullable=False)  # 'brute_force', 'impossible_travel', 'new_device', 'unusual_time'
    severity = db.Column(db.String(20), default='medium', nullable=False)  # 'low', 'medium', 'high'
    description = db.Column(db.Text, nullable=False)
    login_event_id = db.Column(db.Integer, db.ForeignKey('login_events.id'))
    resolved = db.Column(db.Boolean, default=False, nullable=False)
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref='suspicious_activity_alerts')
    login_event = db.relationship('LoginEvent', backref='alerts')


class UserDevice(db.Model):
    __tablename__ = 'user_devices'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    fingerprint = db.Column(db.String(64), nullable=False, index=True)
    user_agent = db.Column(db.String(500))
    last_ip = db.Column(db.String(45))
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    trusted = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'fingerprint', name='uq_user_device'),)

    user = db.relationship('User', backref='devices')


class UserNotificationPreference(db.Model):
    __tablename__ = 'user_notification_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    email_security_alerts = db.Column(db.Boolean, default=True, nullable=False)
    whatsapp_security_alerts = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('notification_preference', uselist=False))


db.Index('ix_login_events_user_created', 'login_events', 'user_id', 'created_at')
db.Index('ix_suspicious_activity_alerts_user_created', 'suspicious_activity_alerts', 'user_id', 'created_at')