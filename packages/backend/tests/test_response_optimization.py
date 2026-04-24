import gzip
import json


def test_large_json_response_is_gzip_compressed(client):
    @client.application.get("/test-large-payload")
    def test_large_payload():
        return {"items": [{"category": "groceries", "amount": 12.34} for _ in range(80)]}

    response = client.get("/test-large-payload", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["Content-Encoding"] == "gzip"
    assert "Accept-Encoding" in response.headers.get("Vary", "")
    assert int(response.headers["X-Original-Content-Length"]) > len(response.data)

    payload = json.loads(gzip.decompress(response.data))
    assert len(payload["items"]) == 80
    assert payload["items"][0]["category"] == "groceries"


def test_response_without_gzip_acceptance_is_not_compressed(client):
    @client.application.get("/test-uncompressed-payload")
    def test_uncompressed_payload():
        return {"items": [{"category": "rent", "amount": 1000} for _ in range(80)]}

    response = client.get("/test-uncompressed-payload")

    assert response.status_code == 200
    assert "Content-Encoding" not in response.headers
    assert response.get_json()["items"][0]["category"] == "rent"


def test_small_response_is_not_compressed(client):
    response = client.get("/health", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert "Content-Encoding" not in response.headers
    assert response.get_json() == {"status": "ok"}
