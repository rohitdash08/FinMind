from flask import Blueprint, request, jsonify
from flask_webhook import emit_event
from backend.app.models import Insight, db

bp = Blueprint('insights', __name__)
    db.session.add(self)
    db.session.commit()
    emit_event('insight_created', insight)

@bp.route('/insights/<int:insight_id>', methods=['GET'])
def get_insight(insight_id):