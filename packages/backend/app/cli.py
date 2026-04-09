from flask import Flask
from app.extensions import db

def register_cli_commands(app: Flask):
    @app.cli.command("init-db")
    def init_db_command():
        """Clear existing data and create new tables."""
        with app.app_context():
            db.drop_all()
            db.create_all()
            app.logger.info("Initialized the database.")

