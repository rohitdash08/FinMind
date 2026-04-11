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

    # Backward-compatible schema patch for existing deployments.
    with app.app_context():
        _ensure_schema_compatibility(app)
        _ensure_job_executions_table(app)

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


def _ensure_job_executions_table(app: Flask) -> None:
    """Create job_executions table and enums if they don't exist (idempotent)."""
    conn = db.engine.raw_connection()
    try:
        cur = conn.cursor()
        # Create enums (safe if exist)
        for enum_name, values in [
            ("job_status", "'PENDING','RUNNING','SUCCESS','FAILED','RETRYING','DEAD'"),
            ("job_type", "'REMINDER','EMAIL','WHATSAPP','IMPORT','INSIGHT','CUSTOM'"),
        ]:
            cur.execute(
                f"DO $$ BEGIN CREATE TYPE {enum_name} AS ENUM ({values}); "
                f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )

        cur.execute("""
            CREATE TABLE IF NOT EXISTS job_executions (
                id SERIAL PRIMARY KEY,
                job_type job_type NOT NULL DEFAULT 'CUSTOM',
                status job_status NOT NULL DEFAULT 'PENDING',
                payload TEXT,
                result TEXT,
                attempt INT NOT NULL DEFAULT 0,
                max_attempts INT NOT NULL DEFAULT 3,
                next_retry_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                dead_reason TEXT,
                dead_at TIMESTAMP,
                source_id INT,
                source_type VARCHAR(50)
            )
        """)

        # Idempotent indexes
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS ix_job_exec_status ON job_executions(status)",
            "CREATE INDEX IF NOT EXISTS ix_job_exec_type_status ON job_executions(job_type, status)",
            "CREATE INDEX IF NOT EXISTS ix_job_exec_retry_at ON job_executions(status, next_retry_at)",
            "CREATE INDEX IF NOT EXISTS ix_job_exec_created_at ON job_executions(created_at)",
        ]:
            cur.execute(idx_sql)

        conn.commit()
    except Exception:
        app.logger.exception("Schema patch failed for job_executions")
        conn.rollback()
    finally:
        conn.close()