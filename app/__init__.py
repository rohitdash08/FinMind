from app.routes.expenses import expenses_bp
from app.routes.reminders import reminders_bp
from app.routes.payee_merchant_aliases import payee_merchant_aliases_bp # NEW IMPORT


def create_app(settings: Settings):
    app = Flask(__name__)
    app.config.from_object(settings)        app.register_blueprint(expenses_bp, url_prefix="/expenses")
        app.register_blueprint(reminders_bp, url_prefix="/reminders")
        app.register_blueprint(payee_merchant_aliases_bp, url_prefix="/payee-merchant-aliases") # NEW REGISTRATION

        # Health check endpoint
        @app.route("/health", methods=["GET"])
        def health():
            return jsonify({"status": "ok"}), HTTPStatus.OK