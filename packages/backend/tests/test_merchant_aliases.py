def test_create_and_list_aliases(client, auth_header):
    r = client.post(
        "/merchant-aliases",
        json={"canonical_name": "Starbucks", "alias": "SBUX"},
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["canonical_name"] == "Starbucks"

    r = client.get("/merchant-aliases", headers=auth_header)
    assert r.status_code == 200
    aliases = r.get_json()
    assert len(aliases) == 1
    assert aliases[0]["alias"] == "SBUX"


def test_duplicate_alias_returns_409(client, auth_header):
    client.post(
        "/merchant-aliases",
        json={"canonical_name": "Starbucks", "alias": "SBUX"},
        headers=auth_header,
    )
    r = client.post(
        "/merchant-aliases",
        json={"canonical_name": "Other", "alias": "SBUX"},
        headers=auth_header,
    )
    assert r.status_code == 409


def test_update_alias(client, auth_header):
    r = client.post(
        "/merchant-aliases",
        json={"canonical_name": "Starbucks", "alias": "SBUX"},
        headers=auth_header,
    )
    alias_id = r.get_json()["id"]

    r = client.patch(
        f"/merchant-aliases/{alias_id}",
        json={"canonical_name": "Starbucks Coffee"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert r.get_json()["canonical_name"] == "Starbucks Coffee"


def test_delete_alias(client, auth_header):
    r = client.post(
        "/merchant-aliases",
        json={"canonical_name": "Starbucks", "alias": "SBUX"},
        headers=auth_header,
    )
    alias_id = r.get_json()["id"]

    r = client.delete(f"/merchant-aliases/{alias_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get("/merchant-aliases", headers=auth_header)
    assert len(r.get_json()) == 0


def test_suggest_aliases(client, auth_header):
    client.post(
        "/expenses",
        json={"amount": 5, "description": "Starbucks Coffee", "date": "2026-02-10"},
        headers=auth_header,
    )
    client.post(
        "/expenses",
        json={"amount": 6, "description": "Starbucks Coffee Grande", "date": "2026-02-11"},
        headers=auth_header,
    )

    r = client.get("/merchant-aliases/suggest", headers=auth_header)
    assert r.status_code == 200
    suggestions = r.get_json()
    assert len(suggestions) >= 1
    assert suggestions[0]["similarity"] > 0.5


def test_merge_aliases(client, auth_header):
    client.post(
        "/merchant-aliases",
        json={"canonical_name": "Starbucks", "alias": "SBUX"},
        headers=auth_header,
    )
    r2 = client.post(
        "/merchant-aliases",
        json={"canonical_name": "Starbs", "alias": "STAR"},
        headers=auth_header,
    )
    target_id = r2.get_json()["id"]

    r = client.post(
        "/merchant-aliases/merge",
        json={"source_id": target_id, "target_id": target_id},
        headers=auth_header,
    )
    assert r.status_code == 200
