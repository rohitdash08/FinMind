from flask import Blueprint

bills_bp = Blueprint("bills", __name__, url_prefix="/bills")

@bills_bp.route("/ping")
def ping():
    return "Bills pong"
