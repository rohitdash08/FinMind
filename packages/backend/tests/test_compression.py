"""
Tests for API response compression middleware.
"""
import pytest
import gzip
import json
from flask import Flask
from app.middleware.compression import compress_response


class TestCompressResponse:
    """Test compress_response decorator."""

    def test_compress_large_response(self, app):
        """Test compression for large responses."""
        with app.test_request_context(
            headers={"Accept-Encoding": "gzip"}
        ):
            # Create large response
            large_data = "x" * 1000
            
            @compress_response(min_size=500)
            def large_response():
                return large_data
            
            response = large_response()
            
            # Should be compressed
            assert response.headers.get("Content-Encoding") == "gzip"
            assert int(response.headers.get("Content-Length", 0)) < len(large_data)

    def test_no_compress_small_response(self, app):
        """Test no compression for small responses."""
        with app.test_request_context(
            headers={"Accept-Encoding": "gzip"}
        ):
            # Create small response
            small_data = "x" * 100
            
            @compress_response(min_size=500)
            def small_response():
                return small_data
            
            response = small_response()
            
            # Should NOT be compressed
            assert "Content-Encoding" not in response.headers

    def test_no_compress_without_gzip_header(self, app):
        """Test no compression when client doesn't accept gzip."""
        with app.test_request_context(
            headers={"Accept-Encoding": "identity"}
        ):
            # Create large response
            large_data = "x" * 1000
            
            @compress_response(min_size=500)
            def large_response():
                return large_data
            
            response = large_response()
            
            # Should NOT be compressed
            assert "Content-Encoding" not in response.headers

    def test_compress_json_response(self, app):
        """Test compression for JSON responses."""
        with app.test_request_context(
            headers={"Accept-Encoding": "gzip"}
        ):
            # Create large JSON response
            large_json = {"data": ["item"] * 100}
            
            @compress_response(min_size=500)
            def json_response():
                return json.dumps(large_json)
            
            response = json_response()
            
            # Should be compressed
            assert response.headers.get("Content-Encoding") == "gzip"

    def test_vary_header_set(self, app):
        """Test Vary header is set for caching."""
        with app.test_request_context(
            headers={"Accept-Encoding": "gzip"}
        ):
            large_data = "x" * 1000
            
            @compress_response(min_size=500)
            def large_response():
                return large_data
            
            response = large_response()
            
            # Should have Vary header
            assert "Vary" in response.headers
            assert "Accept-Encoding" in response.headers["Vary"]

    def test_compressed_data_is_valid(self, app):
        """Test compressed data can be decompressed."""
        with app.test_request_context(
            headers={"Accept-Encoding": "gzip"}
        ):
            original_data = "Hello, World! " * 100
            
            @compress_response(min_size=500)
            def response():
                return original_data
            
            result = response()
            
            # Decompress and verify
            compressed_data = result.get_data()
            decompressed_data = gzip.decompress(compressed_data).decode("utf-8")
            
            assert decompressed_data == original_data

    def test_custom_min_size(self, app):
        """Test custom min_size parameter."""
        with app.test_request_context(
            headers={"Accept-Encoding": "gzip"}
        ):
            # Response of 100 bytes
            data = "x" * 100
            
            # With min_size=200, should NOT compress
            @compress_response(min_size=200)
            def response_200():
                return data
            
            result_200 = response_200()
            assert "Content-Encoding" not in result_200.headers
            
            # With min_size=50, SHOULD compress
            @compress_response(min_size=50)
            def response_50():
                return data
            
            result_50 = response_50()
            assert result_50.headers.get("Content-Encoding") == "gzip"


@pytest.fixture
def app():
    """Create Flask app for testing."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app
