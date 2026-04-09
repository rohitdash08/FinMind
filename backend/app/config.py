import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://user:password@db:5432/finmind'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://redis:6379/0'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'super-secret-jwt'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    CORS_HEADERS = 'Content-Type,Authorization'

    # APScheduler configuration
    SCHEDULER_API_ENABLED = True
    SCHEDULER_JOBSTORES = {
        'default': {'type': 'sqlalchemy', 'url': SQLALCHEMY_DATABASE_URI}
    }
    SCHEDULER_EXECUTORS = {
        'default': {'type': 'threadpool', 'max_workers': 20}
    }

    # Webhook specific configuration
    WEBHOOK_MAX_DELIVERY_ATTEMPTS = int(os.environ.get('WEBHOOK_MAX_DELIVERY_ATTEMPTS', 5))
    WEBHOOK_INITIAL_RETRY_DELAY_SECONDS = int(os.environ.get('WEBHOOK_INITIAL_RETRY_DELAY_SECONDS', 60)) # 1 minute
    WEBHOOK_RETRY_BACKOFF_FACTOR = int(os.environ.get('WEBHOOK_RETRY_BACKOFF_FACTOR', 2)) # Exponential backoff factor

    # Third-party service credentials
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
    SMTP_SERVER = os.environ.get('SMTP_SERVER')
    SMTP_PORT = os.environ.get('SMTP_PORT')
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
    SMTP_SENDER_EMAIL = os.environ.get('SMTP_SENDER_EMAIL')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-3.5-turbo')

    # Flask-Caching config (if used, currently Flask-Redis for cache)
    CACHE_TYPE = 'flask_redis'
    CACHE_REDIS_URL = REDIS_URL# Database
DATABASE_URL=postgresql://user:password@db:5432/finmind

# Redis
REDIS_URL=redis://redis:6379/0

# Flask
SECRET_KEY=supersecretkeyforexample
FLASK_ENV=development # development or production

# JWT
JWT_SECRET_KEY=jwt_super_secret_key

# Webhook Configuration (optional, defaults are set in config.py)
# WEBHOOK_MAX_DELIVERY_ATTEMPTS=5
# WEBHOOK_INITIAL_RETRY_DELAY_SECONDS=60
# WEBHOOK_RETRY_BACKOFF_FACTOR=2

# Twilio (for WhatsApp reminders)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886 # Your Twilio Sandbox number

# Email (e.g., SendGrid, Mailgun, or direct SMTP)
# If using SendGrid:
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# If using direct SMTP:
# SMTP_SERVER=smtp.example.com
# SMTP_PORT=587
# SMTP_USERNAME=your_username
# SMTP_PASSWORD=your_password
# SMTP_SENDER_EMAIL=no-reply@finmind.com

# OpenAI (for insights)
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Gunicorn (for production)
# GUNICORN_BIND=0.0.0.0:8000
# GUNICORN_WORKERS=4
# GUNICORN_TIMEOUT=60