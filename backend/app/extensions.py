from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_caching import Cache
from flask_apscheduler import APScheduler
mail = Mail()
cache = Cache()
scheduler = APScheduler()
jwt = JWTManager()