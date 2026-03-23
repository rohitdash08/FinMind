from flask import Blueprint
from . import auth
from . import savings_goals
api = Blueprint('api', __name__, url_prefix='/api')
api.register_blueprint(savings_goals.bp)