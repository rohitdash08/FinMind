def test_expenses_paginated_response_structure(client, auth_header):
    for i in range(25):
        client.post(
            "/expenses",
            json={
                "amount": 10.0 + i,
                "description": f"Page expense {i}",
                "date": "2026-02-01",
            },
            headers=auth_header,
        )
    r = client.get("/expenses?page=1&page_size=10", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "data" in payload
    assert "pagination" in payload
    pag = payload["pagination"]
    assert pag["page"] == 1
    assert pag["page_size"] == 10
    assert pag["total"] == 25
    assert pag["total_pages"] == 3
    assert pag["has_next"] is True
    assert pag["has_prev"] is False
    assert len(payload["data"]) == 10


def test_expenses_pagination_second_page(client, auth_header):
    for i in range(25):
        client.post(
            "/expenses",
            json={
                "amount": 10.0 + i,
                "description": f"P2 expense {i}",
                "date": "2026-02-02",
            },
            headers=auth_header,
        )
    r = client.get("/expenses?page=2&page_size=10", headers=auth_header)
    assert r.status_code == 200
    pag = r.get_json()["pagination"]
    assert pag["page"] == 2
    assert pag["has_next"] is True
    assert pag["has_prev"] is True
    assert len(r.get_json()["data"]) == 10


def test_expenses_pagination_last_page(client, auth_header):
    for i in range(25):
        client.post(
            "/expenses",
            json={
                "amount": 10.0 + i,
                "description": f"Last page {i}",
                "date": "2026-02-03",
            },
            headers=auth_header,
        )
    r = client.get("/expenses?page=3&page_size=10", headers=auth_header)
    assert r.status_code == 200
    pag = r.get_json()["pagination"]
    assert pag["page"] == 3
    assert pag["has_next"] is False
    assert pag["has_prev"] is True
    assert len(r.get_json()["data"]) == 5


def test_expenses_pagination_out_of_range_returns_empty(client, auth_header):
    r = client.get("/expenses?page=999&page_size=10", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert len(payload["data"]) == 0
    pag = payload["pagination"]
    assert pag["page"] == 999
    assert pag["total"] == 0


def test_expenses_pagination_defaults(client, auth_header):
    r = client.get("/expenses", headers=auth_header)
    assert r.status_code == 200
    payload = r.get_json()
    assert "pagination" in payload


def test_serialization_strip_nulls():
    from app.services.serialization import strip_nulls
    data = {"a": 1, "b": None, "c": {"d": None, "e": 2}, "f": [None, {"g": None}]}
    result = strip_nulls(data)
    assert "b" not in result
    assert "d" not in result["c"]
    assert result["c"]["e"] == 2
    assert result["f"] == [{}]


def test_sparse_fieldsets():
    from app.services.serialization import sparse_fieldsets
    data = {"id": 1, "name": "Test", "amount": 100, "extra": "ignored"}
    result = sparse_fieldsets(data, {"id", "name"})
    assert result == {"id": 1, "name": "Test"}
    assert "amount" not in result
    assert "extra" not in result
