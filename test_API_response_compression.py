"""
Tests for API response compression middleware.
"""
import pytest
import gzip
from unittest.mock import patch, MagicMock
from flask import Flask, make_response
from app.middleware.compression import compress_response
from app.extensions import db


class TestCompressResponseDecorator:
    """Test compress_response decorator."""

    def test_small_response_not_compressed(self):
        """Test that responses below min_size are not compressed."""
        app = Flask(__name__)
        
        @app.route("/small")
        @compress_response(min_size=500)
        def small_response():
            return "small data"
        
        with app.test_client() as client:
            response = client.get("/small")
            assert response.status_code == 200
            assert "Content-Encoding" not in response.headers
            assert response.data == b"small data"

    def test_large_response_compressed_with_gzip(self):
        """Test that large responses are compressed when client accepts gzip."""
        app = Flask(__name__)
        large_data = "x" * 1000  # 1000 bytes > min_size(500)
        
        @app.route("/large")
        @compress_response(min_size=500)
        def large_response():
            return large_data
        
        with app.test_client() as client:
            response = client.get("/large", headers={"Accept-Encoding": "gzip"})
            assert response.status_code == 200
            assert response.headers.get("Content-Encoding") == "gzip"
            assert response.headers.get("Vary") == "Accept-Encoding"
            
            # Verify data can be decompressed
            decompressed = gzip.decompress(response.data)
            assert decompressed == large_data.encode()

    def test_large_response_not_compressed_without_gzip_accept(self):
        """Test that large responses are not compressed when client doesn't accept gzip."""
        app = Flask(__name__)
        large_data = "x" * 1000
        
        @app.route("/large")
        @compress_response(min_size=500)
        def large_response():
            return large_data
        
        with app.test_client() as client:
            response = client.get("/large", headers={"Accept-Encoding": ""})
            assert response.status_code == 200
            assert "Content-Encoding" not in response.headers
            assert response.data == large_data.encode()

    def test_custom_min_size(self):
        """Test custom min_size parameter."""
        app = Flask(__name__)
        
        @app.route("/custom")
        @compress_response(min_size=100)
        def custom_response():
            return "x" * 150  # 150 bytes > min_size(100)
        
        with app.test_client() as client:
            response = client.get("/custom", headers={"Accept-Encoding": "gzip"})
            assert response.headers.get("Content-Encoding") == "gzip"

    def test_json_response_compression(self):
        """Test compression of JSON responses."""
        app = Flask(__name__)
        json_data = {"data": "x" * 1000}
        
        @app.route("/json")
        @compress_response(min_size=500)
        def json_response():
            return json_data
        
        with app.test_client() as client:
            response = client.get("/json", headers={"Accept-Encoding": "gzip"})
            assert response.headers.get("Content-Encoding") == "gzip"
            
            decompressed = gzip.decompress(response.data)
            assert len(decompressed) > 1000

    def test_content_length_header_set(self):
        """Test that Content-Length header is set correctly."""
        app = Flask(__name__)
        large_data = "x" * 1000
        
        @app.route("/large")
        @compress_response(min_size=500)
        def large_response():
            return large_data
        
        with app.test_client() as client:
            response = client.get("/large", headers={"Accept-Encoding": "gzip"})
            content_length = int(response.headers.get("Content-Length", 0))
            assert content_length > 0
            assert content_length < len(large_data)  # Compressed should be smaller


@pytest.fixture
def app():
    """Create application for testing."""
    from app import create_app
    
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db(app):
    """Create database for testing."""
    with app.app_context():
        yield db
