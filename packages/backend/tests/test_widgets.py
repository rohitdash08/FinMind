def test_widgets_requires_auth(client):
    r = client.get("/widgets")
    assert r.status_code in (401, 422)

    r = client.post("/widgets", json=[])
    assert r.status_code in (401, 422)

    r = client.get("/widgets/available")
    assert r.status_code in (401, 422)


def test_save_layout(client, auth_header):
    layout = [
        {"widget_id": "expense_summary", "position": 0, "visible": True, "size": "large"},
        {"widget_id": "bill_calendar", "position": 1, "visible": True, "size": "small"},
    ]
    r = client.post("/widgets", json=layout, headers=auth_header)
    assert r.status_code == 201
    data = r.get_json()
    assert len(data) == 2
    assert data[0]["widget_id"] == "expense_summary"


def test_get_layout(client, auth_header):
    # Initially empty
    r = client.get("/widgets", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []

    # Save and retrieve
    layout = [{"widget_id": "income_tracker", "position": 0, "visible": True, "size": "medium"}]
    client.post("/widgets", json=layout, headers=auth_header)

    r = client.get("/widgets", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data) == 1
    assert data[0]["widget_id"] == "income_tracker"


def test_available_widgets(client, auth_header):
    r = client.get("/widgets/available", headers=auth_header)
    assert r.status_code == 200
    widgets = r.get_json()
    assert len(widgets) >= 3
    assert all("widget_id" in w for w in widgets)
    assert all("name" in w for w in widgets)
    assert all("description" in w for w in widgets)
