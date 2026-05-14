import gzip

import pytest
from flask import jsonify


@pytest.fixture()
def compression_client(app_fixture):
    @app_fixture.get("/_test/large-json")
    def large_json():
        return jsonify(
            items=[
                {
                    "id": idx,
                    "description": f"Large payload expense {idx:02d}",
                    "amount": idx + 1,
                }
                for idx in range(80)
            ]
        )

    return app_fixture.test_client()


def test_gzip_compresses_large_json_response(compression_client):
    r = compression_client.get(
        "/_test/large-json",
        headers={"Accept-Encoding": "gzip"},
    )

    assert r.status_code == 200
    assert r.headers["Content-Encoding"] == "gzip"
    assert "Accept-Encoding" in r.headers["Vary"]
    assert b"Large payload expense" in gzip.decompress(r.data)


def test_gzip_skips_clients_without_accept_encoding(compression_client):
    r = compression_client.get("/_test/large-json")

    assert r.status_code == 200
    assert "Content-Encoding" not in r.headers
    assert b"Large payload expense" in r.data
