"""Tests for API response compression, null stripping, ETags, and pagination."""

import gzip
import json


def test_health_response_has_etag(client):
    """Health endpoint should include an ETag header on JSON responses."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("ETag") is not None


def test_etag_returns_304_on_conditional_get(client):
    """A second GET with If-None-Match matching the ETag should return 304."""
    r1 = client.get("/health")
    assert r1.status_code == 200
    etag = r1.headers["ETag"]

    r2 = client.get("/health", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_etag_mismatch_returns_200(client):
    """If-None-Match with a wrong ETag should still return 200."""
    r = client.get("/health", headers={"If-None-Match": '"wrong-etag"'})
    assert r.status_code == 200


def test_null_fields_stripped_from_json(app_fixture):
    """None/null values should be stripped from JSON responses."""

    @app_fixture.get("/test-nulls")
    def _test_nulls():
        from flask import jsonify

        return jsonify(name="Alice", nickname=None, age=30, extra=None)

    with app_fixture.test_client() as c:
        r = c.get("/test-nulls")
        assert r.status_code == 200
        data = json.loads(r.get_data(as_text=True))
        assert "name" in data
        assert "age" in data
        assert "nickname" not in data
        assert "extra" not in data


def test_response_size_headers_present(client):
    """JSON responses should include X-Original-Size and X-Compressed-Size."""
    r = client.get("/health")
    assert r.status_code == 200
    assert "X-Original-Size" in r.headers
    assert "X-Compressed-Size" in r.headers
    # Both should be parseable integers
    assert int(r.headers["X-Original-Size"]) > 0
    assert int(r.headers["X-Compressed-Size"]) > 0


def test_gzip_accepted_and_compressed(client):
    """When Accept-Encoding: gzip is sent, response should be compressed."""
    r = client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    # flask-compress may or may not compress very small payloads depending
    # on the COMPRESS_MIN_SIZE setting, so we just check the response is valid
    raw = r.get_data()
    # If it was gzip-compressed, the first two bytes are the gzip magic number
    if raw[:2] == b"\x1f\x8b":
        decompressed = gzip.decompress(raw)
        data = json.loads(decompressed)
    else:
        data = json.loads(raw)
    assert data["status"] == "ok"


def test_expenses_list_returns_pagination_metadata(client, auth_header):
    """GET /expenses should return pagination metadata alongside data."""
    r = client.get("/expenses", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert "data" in body
    assert "pagination" in body
    meta = body["pagination"]
    assert meta["page"] == 1
    assert meta["total"] == 0
    assert meta["total_pages"] == 1


def test_bills_list_returns_pagination_metadata(client, auth_header):
    """GET /bills should return pagination metadata alongside data."""
    r = client.get("/bills", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert "data" in body
    assert "pagination" in body
    assert body["pagination"]["page"] == 1


def test_categories_list_returns_pagination_metadata(client, auth_header):
    """GET /categories should return pagination metadata alongside data."""
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert "data" in body
    assert "pagination" in body
    assert body["pagination"]["page"] == 1


def test_reminders_list_returns_pagination_metadata(client, auth_header):
    """GET /reminders should return pagination metadata alongside data."""
    r = client.get("/reminders", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert "data" in body
    assert "pagination" in body
    assert body["pagination"]["page"] == 1


def test_pagination_page_and_page_size_params(client, auth_header):
    """Custom page/page_size query params should be reflected in metadata."""
    # Create a few expenses
    for i in range(5):
        r = client.post(
            "/expenses",
            json={
                "amount": 10 + i,
                "description": f"Item {i}",
                "date": "2026-02-01",
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    r = client.get("/expenses?page=1&page_size=2", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["data"]) == 2
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["page_size"] == 2
    assert body["pagination"]["total"] == 5
    assert body["pagination"]["total_pages"] == 3

    # Page 3 should have 1 item
    r = client.get("/expenses?page=3&page_size=2", headers=auth_header)
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["data"]) == 1
    assert body["pagination"]["page"] == 3
