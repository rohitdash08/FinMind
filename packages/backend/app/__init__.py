import logging
import os
import time

import sentry_sdk
from flask import Flask, g, request
from sentry_sdk.integrations.flask import FlaskIntegration
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Settings
from app.extensions import api, db, jwt, limiter, migrate, oauth, redis_client
from app.routes.auth import auth_bp
from app.routes.bills import bills_bp # New: Import bills blueprint
from app.routes.categories import categories_bp # New: Import categories blueprint
from app.routes.health import health_bp
from app.routes.metrics import metrics_bp
from app.routes.reminders import reminders_bp


def create_app(settings: Settings = None):
    app = Flask(__name__)

    if settings is None:
        settings = Settings()

    app.config.from_object(settings)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    api.init_app(app)
    oauth.init_app(app)
    redis_client.init_app(app)

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(reminders_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(bills_bp) # New: Register bills blueprint
    app.register_blueprint(categories_bp) # New: Register categories blueprint

    # Fix for Nginx proxy headers
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1, x_proto=1, x_prefix=1)

    # Request ID and latency logging
    @app.before_request
    def before_request():
        g.request_id = os.urandom(16).hex()
        g.start_time = time.time()
        # Exclude /metrics from logging by default, as it's noisy
        if request.path != "/metrics":
            app.logger.info(
                "Request started: %s %s", request.method, request.path, extra={"request_id": g.request_id}
            )

    @app.after_request
    def after_request(response):
        response.headers["X-Request-ID"] = g.request_id
        # Exclude /metrics from logging by default
        if request.path != "/metrics":
            response_time = time.time() - g.start_time
            app.logger.info(
                "Request finished: %s %s - Status %s - took %.2fms",
                request.method,
                request.path,
                response.status_code,
                response_time * 1000,
                extra={"request_id": g.request_id},
            )
        return response

    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[
                FlaskIntegration(),
            ],
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Import models to ensure they are registered with SQLAlchemy for migrations
    from app import models  # noqa: F401

    return app

