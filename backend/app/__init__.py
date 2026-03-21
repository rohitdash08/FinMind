from flask import Flask
from .extensions import db, migrate, jwt, cors
from .extensions import init_scheduler
from .routes import register_routes

def create_app(config_name):
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app)
    init_scheduler(app)

    register_routes(app)
