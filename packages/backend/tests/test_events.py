"""Tests for Event-Driven Financial Activity System (Issue #97)."""

import pytest


# ── Helpers ──────────────────────────────────────────────

def _emit(client, hdr, event_type, entity_type, entity_id=None, payload=None):
    data = {"event_type": event_type, "entity_type": entity_type}
    if entity_id is not None:
        data["entity_id"] = entity_id
    if payload:
        data["payload"] = payload
    return client.post("/events/emit", json=data, headers=hdr)


# ── Event Emission ───────────────────────────────────────

class TestEventEmission:
    def test_emit_event(self, client, auth_header):
        r = _emit(client, auth_header, "expense.created", "expense", 1, {"amount": "500"})
        assert r.status_code == 201
        data = r.get_json()
        assert data["event_type"] == "expense.created"
        assert data["entity_type"] == "expense"
        assert data["entity_id"] == 1
        assert data["payload"]["amount"] == "500"

    def test_emit_minimal(self, client, auth_header):
        r = _emit(client, auth_header, "bill.created", "bill")
        assert r.status_code == 201
        assert r.get_json()["entity_id"] is None

    def test_emit_missing_fields(self, client, auth_header):
        r = client.post("/events/emit", json={"event_type": "test"}, headers=auth_header)
        assert r.status_code == 400

    def test_emit_unauthenticated(self, client):
        r = client.post("/events/emit", json={"event_type": "x", "entity_type": "y"})
        assert r.status_code == 401

    def test_emit_with_metadata(self, client, auth_header):
        r = client.post(
            "/events/emit",
            json={
                "event_type": "anomaly.detected",
                "entity_type": "expense",
                "entity_id": 42,
                "payload": {"description": "Unusual spending"},
                "metadata": {"source": "auto-detection"},
            },
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["metadata"]["source"] == "auto-detection"


# ── Event Listing ────────────────────────────────────────

class TestEventListing:
    def test_list_empty(self, client, auth_header):
        r = client.get("/events", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 0
        assert data["events"] == []

    def test_list_events(self, client, auth_header):
        _emit(client, auth_header, "expense.created", "expense", 1)
        _emit(client, auth_header, "bill.created", "bill", 2)
        r = client.get("/events", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] == 2

    def test_filter_by_event_type(self, client, auth_header):
        _emit(client, auth_header, "expense.created", "expense", 1)
        _emit(client, auth_header, "bill.created", "bill", 2)
        r = client.get("/events?event_type=expense.created", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["events"][0]["event_type"] == "expense.created"

    def test_filter_by_entity_type(self, client, auth_header):
        _emit(client, auth_header, "expense.created", "expense", 1)
        _emit(client, auth_header, "bill.created", "bill", 2)
        r = client.get("/events?entity_type=bill", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total"] == 1

    def test_pagination(self, client, auth_header):
        for i in range(5):
            _emit(client, auth_header, "expense.created", "expense", i)
        r = client.get("/events?limit=2&offset=0", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["events"]) == 2
        assert data["total"] == 5

    def test_get_single_event(self, client, auth_header):
        r = _emit(client, auth_header, "expense.created", "expense", 1)
        event_id = r.get_json()["id"]
        r = client.get(f"/events/{event_id}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["id"] == event_id

    def test_get_nonexistent_event(self, client, auth_header):
        r = client.get("/events/9999", headers=auth_header)
        assert r.status_code == 404


# ── Event Replay ─────────────────────────────────────────

class TestEventReplay:
    def test_replay_empty(self, client, auth_header):
        r = client.get("/events/replay", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["count"] == 0

    def test_replay_chronological(self, client, auth_header):
        _emit(client, auth_header, "expense.created", "expense", 1)
        _emit(client, auth_header, "expense.updated", "expense", 1)
        _emit(client, auth_header, "expense.deleted", "expense", 1)
        r = client.get("/events/replay?entity_type=expense&entity_id=1", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["count"] == 3
        # Chronological: created → updated → deleted
        types = [e["event_type"] for e in data["events"]]
        assert types == ["expense.created", "expense.updated", "expense.deleted"]

    def test_replay_filter_entity(self, client, auth_header):
        _emit(client, auth_header, "expense.created", "expense", 1)
        _emit(client, auth_header, "bill.created", "bill", 2)
        r = client.get("/events/replay?entity_type=expense", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["count"] == 1


# ── Event Stats ──────────────────────────────────────────

class TestEventStats:
    def test_stats_empty(self, client, auth_header):
        r = client.get("/events/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_events"] == 0
        assert data["by_event_type"] == {}

    def test_stats_populated(self, client, auth_header):
        _emit(client, auth_header, "expense.created", "expense", 1)
        _emit(client, auth_header, "expense.created", "expense", 2)
        _emit(client, auth_header, "bill.created", "bill", 1)
        r = client.get("/events/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total_events"] == 3
        assert data["by_event_type"]["expense.created"] == 2
        assert data["by_event_type"]["bill.created"] == 1
        assert data["by_entity_type"]["expense"] == 2
        assert data["by_entity_type"]["bill"] == 1


# ── Event Types ──────────────────────────────────────────

class TestEventTypes:
    def test_list_types(self, client, auth_header):
        r = client.get("/events/types", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data) >= 10
        types = [t["event_type"] for t in data]
        assert "expense.created" in types
        assert "bill.paid" in types
        assert "anomaly.detected" in types


# ── Subscriptions ────────────────────────────────────────

class TestSubscriptions:
    def test_subscribe(self, client, auth_header):
        r = client.post(
            "/events/subscribe",
            json={"event_type": "expense.created"},
            headers=auth_header,
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["event_type"] == "expense.created"
        assert data["is_active"] is True

    def test_subscribe_missing_type(self, client, auth_header):
        r = client.post("/events/subscribe", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_list_subscriptions(self, client, auth_header):
        client.post(
            "/events/subscribe",
            json={"event_type": "expense.created"},
            headers=auth_header,
        )
        client.post(
            "/events/subscribe",
            json={"event_type": "bill.paid"},
            headers=auth_header,
        )
        r = client.get("/events/subscriptions", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_unsubscribe(self, client, auth_header):
        r = client.post(
            "/events/subscribe",
            json={"event_type": "expense.created"},
            headers=auth_header,
        )
        sub_id = r.get_json()["id"]
        r = client.delete(f"/events/subscribe/{sub_id}", headers=auth_header)
        assert r.status_code == 200

        r = client.get("/events/subscriptions", headers=auth_header)
        assert len(r.get_json()) == 0

    def test_unsubscribe_not_found(self, client, auth_header):
        r = client.delete("/events/subscribe/9999", headers=auth_header)
        assert r.status_code == 404

    def test_subscribe_idempotent(self, client, auth_header):
        client.post(
            "/events/subscribe",
            json={"event_type": "expense.created"},
            headers=auth_header,
        )
        r = client.post(
            "/events/subscribe",
            json={"event_type": "expense.created"},
            headers=auth_header,
        )
        assert r.status_code == 201
        # Should still be just 1 subscription
        r = client.get("/events/subscriptions", headers=auth_header)
        assert len(r.get_json()) == 1
