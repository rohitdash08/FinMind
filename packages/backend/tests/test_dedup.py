from decimal import Decimal


def test_dedup_score_similarity():
    from app.services.dedup import score_similarity
    a = {"description": "Coffee Shop", "amount": 5.50, "date": "2026-02-10"}
    b = {"description": "Coffee Shop", "amount": 5.50, "date": "2026-02-10"}
    assert score_similarity(a, b) == 1.0

    c = {"description": "Coffee Shop Downtown", "amount": 5.75, "date": "2026-02-11"}
    score = score_similarity(a, c)
    assert 0.5 <= score <= 1.0


def test_dedup_empty_returns_empty(client, auth_header):
    r = client.post("/dedup/check", json={"transactions": []}, headers=auth_header)
    assert r.status_code == 400

    r = client.post(
        "/dedup/check",
        json={"transactions": [{"description": "Test", "amount": 10, "date": "2026-02-10"}]},
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["potential_duplicates"] == 0


def test_dedup_finds_exact_match(client, auth_header):
    client.post(
        "/expenses",
        json={"amount": 15.0, "description": "Lunch", "date": "2026-02-10"},
        headers=auth_header,
    )

    r = client.post(
        "/dedup/check",
        json={"transactions": [{"description": "Lunch", "amount": 15.0, "date": "2026-02-10"}]},
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["potential_duplicates"] == 1
    assert payload["results"][0]["best_score"] >= 0.95


def test_dedup_fuzzy_match(client, auth_header):
    client.post(
        "/expenses",
        json={"amount": 10.0, "description": "Starbucks Coffee", "date": "2026-02-10"},
        headers=auth_header,
    )

    r = client.post(
        "/dedup/check",
        json={
            "transactions": [
                {"description": "Starbucks Coffee Grande", "amount": 10.0, "date": "2026-02-10"}
            ]
        },
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["potential_duplicates"] >= 1


def test_dedup_score_endpoint(client, auth_header):
    r = client.post(
        "/dedup/score",
        json={
            "a": {"description": "Test A", "amount": 10, "date": "2026-02-01"},
            "b": {"description": "Test B", "amount": 10, "date": "2026-02-01"},
        },
        headers=auth_header,
    )
    assert r.status_code == 200
    assert "score" in r.get_json()


def test_dedup_resolve_endpoint(client, auth_header):
    r = client.post(
        "/dedup/resolve",
        json={
            "candidates": [{"description": "Test", "amount": 10, "date": "2026-02-01"}],
            "resolutions": [{"candidate_id": 0, "action": "skip"}],
        },
        headers=auth_header,
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["skipped"] == 1
