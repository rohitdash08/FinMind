def test_create_notification_with_different_priorities_and_groups(client, auth_header):
  for priority in ("low", "medium", "high", "urgent"):
    for group in ("bills", "expenses", "budget", "security", "system"):
      r = client.post(
        "/notifications",
        json={
          "title": f"Test {priority} {group}",
          "message": "Test message",
          "priority": priority,
          "group": group,
        },
        headers=auth_header,
      )
      assert r.status_code == 201
      data = r.get_json()
      assert data["priority"] == priority
      assert data["group"] == group

  r = client.get("/notifications", headers=auth_header)
  assert r.status_code == 200
  assert r.get_json()["total"] == 20


def test_list_notifications_with_filters(client, auth_header):
  client.post(
    "/notifications",
    json={"title": "A", "message": "m", "priority": "high", "group": "bills"},
    headers=auth_header,
  )
  client.post(
    "/notifications",
    json={"title": "B", "message": "m", "priority": "low", "group": "budget"},
    headers=auth_header,
  )

  # Filter by group
  r = client.get("/notifications?group=bills", headers=auth_header)
  data = r.get_json()
  assert data["total"] == 1
  assert data["items"][0]["group"] == "bills"

  # Filter unread
  r = client.get("/notifications?unread_only=true", headers=auth_header)
  data = r.get_json()
  assert data["total"] == 2


def test_mark_single_notification_read(client, auth_header):
  r = client.post(
    "/notifications",
    json={"title": "X", "message": "m", "priority": "medium", "group": "system"},
    headers=auth_header,
  )
  nid = r.get_json()["id"]

  r = client.patch(f"/notifications/{nid}/read", headers=auth_header)
  assert r.status_code == 200
  assert r.get_json()["read"] is True
  assert r.get_json()["read_at"] is not None


def test_mark_read_nonexistent_returns_404(client, auth_header):
  r = client.patch("/notifications/9999/read", headers=auth_header)
  assert r.status_code == 404


def test_mark_all_read(client, auth_header):
  for group in ("bills", "budget", "system"):
    client.post(
      "/notifications",
      json={"title": "T", "message": "m", "group": group},
      headers=auth_header,
    )

  # Mark all in budget group
  r = client.patch("/notifications/read-all?group=budget", headers=auth_header)
  assert r.status_code == 200

  r = client.get("/notifications?unread_only=true", headers=auth_header)
  assert r.get_json()["total"] == 2

  # Mark all remaining
  r = client.patch("/notifications/read-all", headers=auth_header)
  assert r.status_code == 200

  r = client.get("/notifications?unread_only=true", headers=auth_header)
  assert r.get_json()["total"] == 0


def test_unread_count_by_group(client, auth_header):
  for group in ("bills", "bills", "budget", "security"):
    client.post(
      "/notifications",
      json={"title": "T", "message": "m", "group": group},
      headers=auth_header,
    )

  r = client.get("/notifications/unread-count", headers=auth_header)
  assert r.status_code == 200
  data = r.get_json()
  assert data["total"] == 4
  assert data["by_group"]["bills"] == 2
  assert data["by_group"]["budget"] == 1
  assert data["by_group"]["security"] == 1


def test_delete_notification(client, auth_header):
  r = client.post(
    "/notifications",
    json={"title": "Del", "message": "m", "group": "system"},
    headers=auth_header,
  )
  nid = r.get_json()["id"]

  r = client.delete(f"/notifications/{nid}", headers=auth_header)
  assert r.status_code == 200

  r = client.delete(f"/notifications/{nid}", headers=auth_header)
  assert r.status_code == 404


def test_pagination(client, auth_header):
  for i in range(25):
    client.post(
      "/notifications",
      json={"title": f"N{i}", "message": "m", "group": "system"},
      headers=auth_header,
    )

  r = client.get("/notifications?page=1&page_size=10", headers=auth_header)
  data = r.get_json()
  assert data["total"] == 25
  assert len(data["items"]) == 10
  assert data["page"] == 1
  assert data["page_size"] == 10

  r = client.get("/notifications?page=3&page_size=10", headers=auth_header)
  data = r.get_json()
  assert len(data["items"]) == 5

  # Results should be in descending created_at order
  r = client.get("/notifications?page=1&page_size=25", headers=auth_header)
  items = r.get_json()["items"]
  titles = [i["title"] for i in items]
  assert titles[0] == "N24"
  assert titles[-1] == "N0"
