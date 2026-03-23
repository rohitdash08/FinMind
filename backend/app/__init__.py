from flask import Flask
from .config import Config
from .extensions import db, jwt
from .routes import api_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    jwt.init_app(app)
    app.register_blueprint(api_bp)
    return app