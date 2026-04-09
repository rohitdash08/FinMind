from flask import Blueprint

categories_bp = Blueprint("categories", __name__, url_prefix="/categories")

@categories_bp.route("/ping")
def ping():
    return "Categories pong"

