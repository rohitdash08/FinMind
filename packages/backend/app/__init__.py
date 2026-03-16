from flask import Flask, abort, jsonify, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
from sqlalchemy import text
from .config import Settings
from .extensions import db, jwt, redis_client
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
from pathlib import Path


SPA_EXCLUDED_PREFIXES = (
    "/auth",
    "/categories",
    "/expenses",
    "/bills",
    "/reminders",
    "/dashboard",
    "/insights",
    "/health",
    "/metrics",
)


def create_app(settings: Settings | None = None) -> Flask:
    app = Flask(__name__)
    cfg = settings or Settings()

    # Config
    app.config.update(
        SQLALCHEMY_DATABASE_URI=cfg.database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=cfg.max_upload_bytes,
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
    # Keep local/front-end origins explicit so bearer-token requests work
    # without opening wildcard credentialed CORS.
    CORS(app, resources={r"*": {"origins": cfg.cors_origins}})

    # Redis (already global)
    # Blueprint routes
    register_routes(app)

    if _should_serve_spa(app):
        _register_spa_routes(app)

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

    @app.get("/health/ready")
    def health_ready():
        checks = {"database": "error", "redis": "error"}
        status_code = 200

        try:
            db.session.execute(text("SELECT 1"))
            checks["database"] = "connected"
        except Exception:
            app.logger.exception("Database readiness check failed")
            db.session.rollback()
            status_code = 503

        try:
            redis_client.ping()
            checks["redis"] = "connected"
        except Exception:
            app.logger.exception("Redis readiness check failed")
            status_code = 503

        status = "ok" if status_code == 200 else "error"
        return jsonify(status=status, checks=checks), status_code

    @app.get("/metrics")
    def metrics():
        obs = app.extensions["observability"]
        return obs.metrics_response()

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify(error="internal server error"), 500

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return jsonify(error="upload too large"), 413

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


def _should_serve_spa(app: Flask) -> bool:
    if os.getenv("FINMIND_SERVE_SPA", "0") != "1":
        return False
    if not app.static_folder:
        return False
    return Path(app.static_folder, "index.html").exists()


def _register_spa_routes(app: Flask) -> None:
    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def serve_spa(path: str):
        requested_path = f"/{path}" if path else "/"
        if any(
            requested_path == prefix or requested_path.startswith(f"{prefix}/")
            for prefix in SPA_EXCLUDED_PREFIXES
        ):
            abort(404)

        static_root = Path(app.static_folder or "")
        asset_path = static_root / path
        if path and asset_path.is_file():
            return send_from_directory(str(static_root), path)

        return send_from_directory(str(static_root), "index.html")


def _ensure_schema_compatibility(app: Flask) -> None:
    """Apply minimal compatibility ALTERs for existing deployments."""
    if db.engine.dialect.name != "postgresql":
        return
    try:
        conn = db.engine.raw_connection()
    except Exception:
        app.logger.warning(
            "Skipping schema compatibility patch until database is reachable",
            exc_info=True,
        )
        return
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
