from flask_sqlalchemy import SQLAlchemy
from flask_redis import FlaskRedis
from flask_jwt_extended import JWTManager
from flask_apscheduler import APScheduler
import logging

db = SQLAlchemy()
redis_client = FlaskRedis()
jwt = JWTManager()
scheduler = APScheduler()

# Initialize a logger for webhook specific events
webhook_logger = logging.getLogger('finmind.webhooks')
webhook_logger.setLevel(logging.INFO)
# Prevent propagation to the root logger if desired, to manage output specifically
# webhook_logger.propagate = False 
# Example handler (could be configured to file, console, etc. in app setup)
if not webhook_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    webhook_logger.addHandler(handler)