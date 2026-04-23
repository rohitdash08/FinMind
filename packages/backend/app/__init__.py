from flask import Flask, jsonify
from .config import Settings
from .extensions import db, jwt
from .routes import register_routes
from .observability import (
    Observability,
    configure_logging,
    finalize_request,
    init_request_context,
)
from flask_cors import CORS
import click
import os
import logging
from datetime import timedelta
from .models import Reminder


def create_app(settings: Settings | None = None) -> Flask:
    app = Flask(__name__)
    cfg = settings or Settings()

    # Config
    app.config.update(
        SQLALCHEMY_DATABASE_URI=cfg.database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY=cfg.jwt_secret,
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=cfg.jwt_access_minutes),
        JWT_REFRESH_TOKEN_EXPIRES=timedelta(hours=cfg.jwt_refresh_hours),
        OPENAI_API_KEY=cfg.openai_api_key,
        GEMINI_API_KEY=cfg.gemini_api_key,
        GEMINI_MODEL=cfg.gemini_model,
        TWILIO_ACCOUNT_SID=cfg.twilio_account_sid,
        TWILIO_AUTH_TOKEN=cfg.twilio_auth_token,
        TWILIO_WHATSAPP_FROM=cfg.twilio_whatsapp_from,
        EMAIL_FROM=cfg.email_from,
    )

    # Logging
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    configure_logging(log_level)
    logger = logging.getLogger("finmind")
    logger.info("Starting FinMind backend with log level %s", log_level)

    # Extensions
    db.init_app(app)
    jwt.init_app(app)
    app.extensions["observability"] = Observability()
    # CORS for local dev frontend
    CORS(app, resources={r"*": {"origins": "*"}}, supports_credentials=True)

    # Redis (already global)
    # Blueprint routes
    register_routes(app)

    # Backward-compatible schema patch for existing databases.
    with app.app_context():
        _ensure_schema_compatibility(app)

    @app.before_request
    def _before_request():
        init_request_context()

    @app.after_request
    def _after_request(response):
        return finalize_request(response)

    @app.get("/health")
    def health():
        return jsonify(status="ok"), 200

    @app.get("/metrics")
    def metrics():
        obs = app.extensions["observability"]
        return obs.metrics_response()

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify(error="internal server error"), 500

    @app.cli.command("init-db")
    def init_db():
        """Initialize database schema from db/schema.sql"""
        schema_path = os.path.join(os.path.dirname(__file__), "db", "schema.sql")
        with app.app_context():
            with open(schema_path, "r", encoding="utf-8") as f:
                sql = f.read()
            conn = db.engine.raw_connection()
            try:
                cur = conn.cursor()
                cur.execute(sql)
                conn.commit()
                click.echo("Database initialized.")
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Background task: send_reminder handler
    # ------------------------------------------------------------------
    from .services import taskqueue
    from .services.reminders import send_reminder

    def _handle_send_reminder(payload: dict) -> bool:
        reminder_id = payload.get("reminder_id")
        if reminder_id is None:
            return False
        reminder = db.session.get(Reminder, reminder_id)
        if reminder is None:
            return False
        ok = send_reminder(reminder)
        if ok:
            reminder.sent = True
            db.session.commit()
        return ok

    taskqueue.register_handler("send_reminder", _handle_send_reminder)

    @app.cli.command("worker")
    @click.option("--poll-interval", default=1.0, help="Seconds between polls")
    @click.option("--max-iterations", default=None, type=int, help="Stop after N iterations")
    def worker(poll_interval, max_iterations):
        """Run the background task worker."""
        taskqueue.worker_loop(poll_interval=poll_interval, max_iterations=max_iterations)

    return app


def _ensure_schema_compatibility(app: Flask) -> None:
    """Apply minimal compatibility ALTERs for existing deployments."""
    if db.engine.dialect.name != "postgresql":
        return
    conn = db.engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS preferred_currency VARCHAR(10)
            NOT NULL DEFAULT 'INR'
            """
        )
        conn.commit()
    except Exception:
        app.logger.exception(
            "Schema compatibility patch failed for users.preferred_currency"
        )
        conn.rollback()
    finally:
        conn.close()
