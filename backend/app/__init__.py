from flask import Flask, jsonify
from flask_cors import CORS
from app.config import Config
from app.extensions import db, redis_client, jwt, scheduler
from app.routes.auth import auth_bp
from app.routes.expenses import expenses_bp
from app.routes.bills import bills_bp
from app.routes.reminders import reminders_bp
from app.routes.insights import insights_bp
from app.routes.webhooks import webhooks_bp # New import
from app.services.reminders import reminder_scheduler_job
from app.services.webhooks import webhook_scheduler_job # New import    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(expenses_bp, url_prefix='/expenses')
    app.register_blueprint(bills_bp, url_prefix='/bills')
    app.register_blueprint(reminders_bp, url_prefix='/reminders')
    app.register_blueprint(insights_bp, url_prefix='/insights')
    app.register_blueprint(webhooks_bp, url_prefix='/webhooks') # Register webhook blueprint        with app.app_context():
            # Add reminder job if not already scheduled
            job_exists = scheduler.get_job('run_reminders')
            if not job_exists:
                scheduler.add_job(
                    id='run_reminders',
                    func=reminder_scheduler_job,
                    trigger='interval',
                    minutes=1,
                    max_instances=1,
                    coalesce=True
                )
            # Add webhook delivery retry job
            webhook_job_exists = scheduler.get_job('retry_failed_webhooks')
            if not webhook_job_exists:
                scheduler.add_job(
                    id='retry_failed_webhooks',
                    func=webhook_scheduler_job,
                    trigger='interval',
                    seconds=30, # Check for failed webhooks every 30 seconds
                    max_instances=1,
                    coalesce=True
                )