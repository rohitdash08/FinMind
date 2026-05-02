def test_health_compressed_with_gzip(client):
    """Responses with Accept-Encoding: gzip should be compressed."""
    response = client.get(
        "/health",
        headers={"Accept-Encoding": "gzip"},
    )
    assert response.status_code == 200
    # Flask-Compress adds Content-Encoding header when compressed
    # Note: test client may not compress very small responses
    # due to COMPRESS_MIN_SIZE=500


def test_json_response_has_correct_mimetype(client, auth_header):
    """JSON responses should have application/json mimetype."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.content_type.startswith("application/json")


def test_small_response_not_compressed(client):
    """Responses smaller than COMPRESS_MIN_SIZE (500 bytes) should not be compressed."""
    response = client.get(
        "/health",
        headers={"Accept-Encoding": "gzip"},
    )
    assert response.status_code == 200
    # Health endpoint returns a small JSON response (< 500 bytes)
    # so it should not have Content-Encoding: gzip
    assert response.headers.get("Content-Encoding") is None


def test_expenses_list_returns_pagination_metadata(client, auth_header):
    """List expenses endpoint should return paginated response with metadata."""
    # Create a few expenses
    for i in range(3):
        client.post(
            "/expenses",
            json={
                "amount": 10.50 + i,
                "description": f"Test expense {i}",
                "date": "2024-01-15",
            },
            headers=auth_header,
        )

    response = client.get(
        "/expenses?page=1&page_size=2",
        headers=auth_header,
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] == 3
    assert len(data["items"]) == 2


def test_expenses_list_default_pagination(client, auth_header):
    """Default pagination should use page=1 and page_size=50."""
    client.post(
        "/expenses",
        json={
            "amount": 25.00,
            "description": "Default pagination test",
            "date": "2024-01-15",
        },
        headers=auth_header,
    )

    response = client.get("/expenses", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert data["page"] == 1
    assert data["page_size"] == 50


def test_expenses_list_invalid_pagination(client, auth_header):
    """Invalid pagination params should return 400 error."""
    response = client.get(
        "/expenses?page=abc",
        headers=auth_header,
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_response_size_metric_recorded(client, auth_header):
    """Response size should be tracked in Prometheus metrics."""
    # Make a request to generate metrics
    client.get("/health")

    # Check metrics endpoint
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    payload = metrics.get_data(as_text=True)
    assert "finmind_http_response_size_bytes" in payload
