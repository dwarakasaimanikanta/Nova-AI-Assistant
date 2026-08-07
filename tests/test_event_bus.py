"""
tests/test_event_bus.py
-----------------------
Unit tests verifying the EventBus, EventRegistry, EventSubscriber, and EventPublisher implementations.
"""

import time
import threading
from unittest.mock import MagicMock
import pytest

from core.event_bus import (
    Event, EventBus, EventRegistry, EventSubscriber, EventPublisher,
    EventType, EventPriority
)


def test_event_properties():
    """Verify Event object stores parameters, priorities, and timestamps accurately."""
    payload = {"status": "ok"}
    event = Event(
        event_type=EventType.VOICE_DETECTED,
        source="VoiceManager",
        payload=payload,
        priority=EventPriority.HIGH
    )

    assert event.type == EventType.VOICE_DETECTED
    assert event.source == "VoiceManager"
    assert event.payload == payload
    assert event.priority == EventPriority.HIGH
    assert event.timestamp > 0.0
    
    data = event.to_dict()
    assert data["type"] == EventType.VOICE_DETECTED
    assert data["source"] == "VoiceManager"
    assert data["priority"] == int(EventPriority.HIGH)


def test_event_bus_publish_and_subscribe():
    """Verify subscribers receive matched published events successfully."""
    bus = EventBus()
    received_events = []

    def callback(ev: Event):
        received_events.append(ev)

    subscriber = EventSubscriber("TestSub", callback)
    bus.subscribe(EventType.VOICE_DETECTED, subscriber)

    # Publish matching event
    ev1 = Event(EventType.VOICE_DETECTED, "Test")
    bus.publish(ev1)

    assert len(received_events) == 1
    assert received_events[0] is ev1

    # Publish non-matching event
    ev2 = Event(EventType.BROWSER_NAVIGATED, "Test")
    bus.publish(ev2)

    assert len(received_events) == 1  # count unchanged


def test_event_bus_unsubscribe():
    """Verify unsubscribing prevents subsequent events from triggering callback."""
    bus = EventBus()
    received_events = []

    def callback(ev: Event):
        received_events.append(ev)

    subscriber = EventSubscriber("TestSub", callback)
    bus.subscribe(EventType.VOICE_DETECTED, subscriber)

    bus.publish(Event(EventType.VOICE_DETECTED, "Test"))
    assert len(received_events) == 1

    bus.unsubscribe(EventType.VOICE_DETECTED, subscriber)
    bus.publish(Event(EventType.VOICE_DETECTED, "Test"))
    assert len(received_events) == 1  # count remains 1


def test_event_bus_wildcard_subscription():
    """Verify wildcard '*' subscriber receives all published events."""
    bus = EventBus()
    received_events = []

    subscriber = EventSubscriber("WildcardSub", lambda ev: received_events.append(ev))
    bus.subscribe("*", subscriber)

    bus.publish(Event(EventType.VOICE_DETECTED, "Src1"))
    bus.publish(Event(EventType.BROWSER_NAVIGATED, "Src2"))

    assert len(received_events) == 2
    assert received_events[0].type == EventType.VOICE_DETECTED
    assert received_events[1].type == EventType.BROWSER_NAVIGATED


def test_ordered_delivery():
    """Verify events are dispatched to subscribers in registration order."""
    bus = EventBus()
    order = []

    sub1 = EventSubscriber("Sub1", lambda ev: order.append("Sub1"))
    sub2 = EventSubscriber("Sub2", lambda ev: order.append("Sub2"))

    bus.subscribe(EventType.CUSTOM, sub1)
    bus.subscribe(EventType.CUSTOM, sub2)

    bus.publish(Event(EventType.CUSTOM, "Src"))
    assert order == ["Sub1", "Sub2"]


def test_subscriber_exception_isolation():
    """Verify failure in one subscriber callback does not crash bus or prevent delivery to others."""
    bus = EventBus()
    delivered = []

    def failing_callback(ev: Event):
        raise RuntimeError("Callback failure")

    sub1 = EventSubscriber("FailingSub", failing_callback)
    sub2 = EventSubscriber("SuccessSub", lambda ev: delivered.append(ev))

    bus.subscribe(EventType.CUSTOM, sub1)
    bus.subscribe(EventType.CUSTOM, sub2)

    # Publish should complete cleanly despite sub1 raising exception
    event = Event(EventType.CUSTOM, "Src")
    bus.publish(event)

    assert len(delivered) == 1
    assert delivered[0] is event


def test_publisher_wrapper():
    """Verify EventPublisher wraps event building and forwards calls to the bus."""
    bus = EventBus()
    received = []

    subscriber = EventSubscriber("Sub", lambda ev: received.append(ev))
    bus.subscribe(EventType.SYSTEM_STARTUP, subscriber)

    publisher = EventPublisher("MyManager", bus)
    publisher.publish_event(EventType.SYSTEM_STARTUP, {"boot": "fast"})

    assert len(received) == 1
    assert received[0].source == "MyManager"
    assert received[0].payload == {"boot": "fast"}


def test_thread_safety():
    """Verify EventBus handles concurrent publish and subscribe calls safely from multiple threads."""
    bus = EventBus()
    subscriber = EventSubscriber("ThreadSub", lambda ev: None)

    threads = []
    # Spawn thread to publish events
    def publisher_loop():
        for _ in range(50):
            bus.publish(Event(EventType.CUSTOM, "Thread"))
            time.sleep(0.001)

    # Spawn thread to subscribe/unsubscribe
    def subscriber_loop():
        for _ in range(50):
            bus.subscribe(EventType.CUSTOM, subscriber)
            bus.unsubscribe(EventType.CUSTOM, subscriber)
            time.sleep(0.001)

    t1 = threading.Thread(target=publisher_loop)
    t2 = threading.Thread(target=subscriber_loop)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()

    # If it completed without raising ConcurrentModification / RuntimeError, it is successful
    assert len(bus.get_history()) > 0
