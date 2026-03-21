from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.redis import RedisJobStore
import logging

db = SQLAlchemy()
jwt = JWTManager()

scheduler = BackgroundScheduler(
    jobstores={'default': RedisJobStore(host='localhost', port=6379, db=0)},
    executors={'default': ThreadPoolExecutor(20)},
    job_defaults={'coalesce': False, 'max_instances': 3},
    timezone='UTC'
)

def init_extensions(app):
    db.init_app(app)
    jwt.init_app(app)
    scheduler.start()
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(logging.StreamHandler())