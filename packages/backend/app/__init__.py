from flask import Flask
from .extensions import db, jwt, mail, cors, limiter, migrate, metrics, scheduler, redis_client
from .config import Settings
from .cli import register_cli_commands
from .routes.auth import auth_bp
from .routes.categories import categories_bp
from .routes.bills import bills_bp
from .routes.expenses import expenses_bp
from .routes.insights import insights_bp

def create_app(settings: Settings):
    app = Flask(__name__)
    app.config.from_object(settings)

    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    cors.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)
    metrics.init_app(app)
    scheduler.init_app(app)

    with app.app_context():
        app.register_blueprint(auth_bp)
        app.register_blueprint(categories_bp)
        app.register_blueprint(bills_bp)
        app.register_blueprint(expenses_bp)
        app.register_blueprint(insights_bp)

        register_cli_commands(app)

        @app.route("/health")
        def health_check():
            return {"status": "ok"}

        if settings.schedule_jobs and not app.testing:
            from .tasks import schedule_all_jobs
            schedule_all_jobs(scheduler, app)

    return app

