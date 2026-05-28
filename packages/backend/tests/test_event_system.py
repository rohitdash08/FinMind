"""Tests for event-driven system."""

import pytest


class TestEventBus:
    def test_publish_subscribe(self):
        from app.services.event_system import EventBus, Event
        bus = EventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe("test.event", handler)
        event = Event(event_type="test.event", payload={"key": "value"})
        bus.publish(event)

        assert len(received) == 1
        assert received[0].payload["key"] == "value"

    def test_multiple_handlers(self):
        from app.services.event_system import EventBus, Event
        bus = EventBus()
        results = []

        bus.subscribe("test.multi", lambda e: results.append("h1"))
        bus.subscribe("test.multi", lambda e: results.append("h2"))

        bus.publish(Event(event_type="test.multi"))
        assert len(results) == 2

    def test_event_log(self):
        from app.services.event_system import EventBus, Event
        bus = EventBus()

        bus.publish(Event(event_type="t1", user_id="u1"))
        bus.publish(Event(event_type="t2", user_id="u1"))
        bus.publish(Event(event_type="t1", user_id="u2"))

        log = bus.get_event_log(user_id="u1")
        assert len(log) == 2

        log_filtered = bus.get_event_log(event_type="t1")
        assert len(log_filtered) == 2

    def test_wildcard_handler(self):
        from app.services.event_system import EventBus, Event
        bus = EventBus()
        all_events = []

        bus.subscribe_all(lambda e: all_events.append(e))
        bus.publish(Event(event_type="a.b"))
        bus.publish(Event(event_type="c.d"))

        assert len(all_events) == 2

    def test_handler_error_isolation(self):
        from app.services.event_system import EventBus, Event
        bus = EventBus()

        def bad_handler(e):
            raise ValueError("test error")

        good_results = []
        bus.subscribe("test.error", bad_handler)
        bus.subscribe("test.error", lambda e: good_results.append("ok"))

        result = bus.publish(Event(event_type="test.error"))
        assert len(good_results) == 1  # Good handler still runs


class TestBuiltInHandlers:
    def test_threshold_handler(self):
        from app.services.event_system import handle_transaction_threshold, Event
        event = Event(event_type="transaction.threshold_exceeded",
                      payload={"amount": 5000, "threshold": 1000})
        result = handle_transaction_threshold(event)
        assert result["alert"] is True

    def test_large_transaction_flagged(self):
        from app.services.event_system import handle_large_transaction, Event
        event = Event(event_type="transaction.large_detected",
                      payload={"amount": 300, "average_amount": 50})
        result = handle_large_transaction(event)
        assert result["flagged"] is True
