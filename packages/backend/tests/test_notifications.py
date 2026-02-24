"""Tests for notification priority & grouping (#122)."""


def _create_notif(client, auth_header, title, message, priority="MEDIUM", group="SYSTEM"):
    r = client.post("/notifications", json={
        "title": title, "message": message, "priority": priority, "group": group,
    }, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


class TestNotificationCRUD:
    def test_create_and_list(self, client, auth_header):
        _create_notif(client, auth_header, "Test", "Hello")
        r = client.get("/notifications", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) >= 1

    def test_create_validation(self, client, auth_header):
        r = client.post("/notifications", json={"title": "", "message": ""}, headers=auth_header)
        assert r.status_code == 400

    def test_priority_ordering(self, client, auth_header):
        _create_notif(client, auth_header, "Low", "low msg", "LOW", "SYSTEM")
        _create_notif(client, auth_header, "Critical", "urgent", "CRITICAL", "BILLS")
        _create_notif(client, auth_header, "High", "high msg", "HIGH", "BUDGETS")
        r = client.get("/notifications", headers=auth_header)
        data = r.get_json()
        priorities = [n["priority"] for n in data]
        # CRITICAL should come before HIGH, HIGH before LOW
        crit_idx = next(i for i, p in enumerate(priorities) if p == "CRITICAL")
        high_idx = next(i for i, p in enumerate(priorities) if p == "HIGH")
        low_idx = next(i for i, p in enumerate(priorities) if p == "LOW")
        assert crit_idx < high_idx < low_idx


class TestGrouping:
    def test_grouped_endpoint(self, client, auth_header):
        _create_notif(client, auth_header, "Bill due", "Pay rent", "HIGH", "BILLS")
        _create_notif(client, auth_header, "Budget warn", "80% used", "MEDIUM", "BUDGETS")
        r = client.get("/notifications/grouped", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "BILLS" in data
        assert "BUDGETS" in data

    def test_filter_by_group(self, client, auth_header):
        _create_notif(client, auth_header, "Bill", "msg", "HIGH", "BILLS")
        _create_notif(client, auth_header, "Insight", "msg", "LOW", "INSIGHTS")
        r = client.get("/notifications?group=BILLS", headers=auth_header)
        data = r.get_json()
        assert all(n["group"] == "BILLS" for n in data)


class TestReadStatus:
    def test_mark_read(self, client, auth_header):
        n = _create_notif(client, auth_header, "Test", "msg")
        assert n["read"] is False
        r = client.post("/notifications/read", json={"ids": [n["id"]]}, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["marked"] == 1

    def test_mark_all_read(self, client, auth_header):
        _create_notif(client, auth_header, "A", "msg")
        _create_notif(client, auth_header, "B", "msg")
        r = client.post("/notifications/read-all", headers=auth_header)
        assert r.status_code == 200

    def test_unread_filter(self, client, auth_header):
        n = _create_notif(client, auth_header, "Unread", "msg")
        _create_notif(client, auth_header, "Read", "msg")
        client.post("/notifications/read", json={"ids": [n["id"]]}, headers=auth_header)
        r = client.get("/notifications?unread=true", headers=auth_header)
        data = r.get_json()
        assert all(not n["read"] for n in data)

    def test_mark_read_empty_ids(self, client, auth_header):
        r = client.post("/notifications/read", json={"ids": []}, headers=auth_header)
        assert r.status_code == 400
