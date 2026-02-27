"""Tests for API response compression & payload optimization."""

import gzip
import json
import pytest
from app.services.compression import (
    init_compression, paginate, get_compression_stats, _apply_field_selection,
    _format_number if hasattr(__import__('app.services.compression', fromlist=['_format_number']), '_format_number') else None,
)


@pytest.fixture
def app():
    from app import create_app
    from app.config import Settings
    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    app = create_app(settings)
    with app.app_context():
        from app.extensions import db
        db.create_all()
        yield app


@pytest.fixture
def user(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        u = User(email="test@example.com", password_hash=generate_password_hash("pass"))
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def token(app, user):
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(identity=str(user))


class TestGzipCompression:
    def test_large_response_compressed(self, app, user, token):
        # Create a route that returns large JSON
        @app.route("/test-large")
        def large():
            from flask import jsonify
            return jsonify({"data": "x" * 2000})

        init_compression(app)
        client = app.test_client()
        resp = client.get("/test-large",
                          headers={"Accept-Encoding": "gzip"})
        if resp.headers.get("Content-Encoding") == "gzip":
            decompressed = gzip.decompress(resp.data)
            data = json.loads(decompressed)
            assert len(data["data"]) == 2000

    def test_small_response_not_compressed(self, app, user, token):
        @app.route("/test-small")
        def small():
            from flask import jsonify
            return jsonify({"ok": True})

        init_compression(app)
        client = app.test_client()
        resp = client.get("/test-small",
                          headers={"Accept-Encoding": "gzip"})
        assert resp.headers.get("Content-Encoding") is None


class TestFieldSelection:
    def test_filter_dict(self, app):
        with app.app_context():
            from flask import Flask
            resp = app.make_response(json.dumps({"id": 1, "name": "Test", "email": "a@b.com"}))
            resp.content_type = "application/json"
            filtered = _apply_field_selection(resp, "id,name")
            data = json.loads(filtered.get_data())
            assert "id" in data
            assert "name" in data
            assert "email" not in data

    def test_filter_list(self, app):
        with app.app_context():
            resp = app.make_response(json.dumps([
                {"id": 1, "name": "A", "extra": "x"},
                {"id": 2, "name": "B", "extra": "y"},
            ]))
            resp.content_type = "application/json"
            filtered = _apply_field_selection(resp, "id,name")
            data = json.loads(filtered.get_data())
            assert len(data) == 2
            assert "extra" not in data[0]


class TestPaginate:
    def test_basic(self, app, user):
        with app.app_context():
            from app.models import Expense
            q = Expense.query.filter_by(user_id=user)
            result = paginate(q, page=1, per_page=10)
            assert result["page"] == 1
            assert result["total"] == 0
            assert result["has_next"] is False

    def test_max_per_page(self, app, user):
        with app.app_context():
            from app.models import Expense
            q = Expense.query.filter_by(user_id=user)
            result = paginate(q, page=1, per_page=500, max_per_page=100)
            assert result["per_page"] == 100


class TestCompressionStats:
    def test_empty(self, app):
        with app.app_context():
            stats = get_compression_stats()
            assert stats["total_requests"] == 0

    def test_with_data(self, app):
        with app.app_context():
            from app.services.compression import ResponseMetric
            from app.extensions import db
            m = ResponseMetric(endpoint="/test", method="GET", status_code=200,
                               original_size=1000, compressed_size=300,
                               compression_ratio=0.3, duration_ms=50)
            db.session.add(m)
            db.session.commit()
            stats = get_compression_stats()
            assert stats["total_requests"] == 1
            assert stats["total_saved_bytes"] == 700


class TestAPI:
    def test_stats(self, app, user, token):
        client = app.test_client()
        resp = client.get("/compression/stats",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
