import os
from flask_webhook import WebhookConfig

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'your_jwt_secret_key'
    WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET') or 'your_webhook_secret_key'
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL') or 'https://your-webhook-url.com'
    WEBHOOK_CONFIG = WebhookConfig(secret=WEBHOOK_SECRET, url=WEBHOOK_URL)