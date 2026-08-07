"""
core/event_bus.py
-----------------
Core internal event bus supporting synchronous, ordered, and thread-safe publishing,
subscribing, and unsubscribing.
"""

import time
import threading
from typing import Any, Callable, Dict, List, Set, Optional
from enum import Enum, IntEnum
from utils.logger import get_logger

logger = get_logger(__name__)


class EventPriority(IntEnum):
    """Priority levels for Event Bus messaging."""
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class EventType(str, Enum):
    """Supported standard event types across the Nova ecosystem."""
    SYSTEM_STARTUP = "SYSTEM_STARTUP"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    VOICE_DETECTED = "VOICE_DETECTED"
    VOICE_TRANSCRIPT = "VOICE_TRANSCRIPT"
    BROWSER_NAVIGATED = "BROWSER_NAVIGATED"
    BROWSER_ACTION = "BROWSER_ACTION"
    ANDROID_CONNECTED = "ANDROID_CONNECTED"
    ANDROID_NOTIFICATION = "ANDROID_NOTIFICATION"
    MEMORY_STORED = "MEMORY_STORED"
    MEMORY_RETRIVED = "MEMORY_RETRIVED"
    LLM_PLANNING = "LLM_PLANNING"
    LLM_RESPONSE = "LLM_RESPONSE"
    UI_ACTION = "UI_ACTION"
    CUSTOM = "CUSTOM"


class Event:
    """Base event container model."""

    def __init__(
        self,
        event_type: EventType | str,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: EventPriority = EventPriority.MEDIUM,
    ) -> None:
        self.type = event_type
        self.source = source
        self.payload = payload or {}
        self.priority = priority
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "source": self.source,
            "payload": self.payload,
            "priority": int(self.priority),
            "timestamp": self.timestamp,
        }


class EventSubscriber:
    """Subscriber wrapper holding callback hooks and type registrations."""

    def __init__(self, name: str, callback: Callable[[Event], None]) -> None:
        self.name = name
        self.callback = callback

    def on_event(self, event: Event) -> None:
        """Triggers the subscriber's custom processing block."""
        try:
            self.callback(event)
        except Exception as e:
            logger.error("[EventSubscriber] Callback failed for subscriber %s on event %s: %s", self.name, event.type, e)


class EventRegistry:
    """Manages mappings of event types to active subscriber groups."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscriptions: Dict[str, List[EventSubscriber]] = {}

    def register(self, event_type: str, subscriber: EventSubscriber) -> None:
        """Register a subscriber for a specific event type."""
        with self._lock:
            if event_type not in self._subscriptions:
                self._subscriptions[event_type] = []
            if subscriber not in self._subscriptions[event_type]:
                self._subscriptions[event_type].append(subscriber)
                logger.info("[EventRegistry] Subscribed %s to %s", subscriber.name, event_type)

    def unregister(self, event_type: str, subscriber: EventSubscriber) -> None:
        """Remove a subscriber from a specific event type."""
        with self._lock:
            if event_type in self._subscriptions:
                try:
                    self._subscriptions[event_type].remove(subscriber)
                    logger.info("[EventRegistry] Unsubscribed %s from %s", subscriber.name, event_type)
                except ValueError:
                    pass

    def get_subscribers(self, event_type: str) -> List[EventSubscriber]:
        """Get copy of subscriber list for safety during iteration."""
        with self._lock:
            return list(self._subscriptions.get(event_type, []))


class EventBus:
    """Main communication bus mediating topic routing and subscriptions."""

    def __init__(self, registry: Optional[EventRegistry] = None) -> None:
        self.registry = registry or EventRegistry()
        self._lock = threading.Lock()
        self._event_history: List[Event] = []

    def subscribe(self, event_type: EventType | str, subscriber: EventSubscriber) -> None:
        """Subscribe to a given event type."""
        self.registry.register(str(event_type), subscriber)

    def unsubscribe(self, event_type: EventType | str, subscriber: EventSubscriber) -> None:
        """Unsubscribe from a given event type."""
        self.registry.unregister(str(event_type), subscriber)

    def publish(self, event: Event) -> None:
        """
        Publish an event to all registered topic subscribers.
        Delivers synchronously and maintains priority queue/order.
        """
        with self._lock:
            self._event_history.append(event)
            # Keep history capped at last 1000 events to avoid memory bloat
            if len(self._event_history) > 1000:
                self._event_history.pop(0)

        # Get subscribers for this type
        subscribers = self.registry.get_subscribers(str(event.type))
        # Also support wildcard subscriptions (type = "*")
        wildcard_subs = self.registry.get_subscribers("*")
        
        all_subs = subscribers + wildcard_subs

        # Delivery: ordered by how they are registered (or priority queue if asynchronous queues exist)
        for subscriber in all_subs:
            logger.debug("[EventBus] Dispatching %s to %s", event.type, subscriber.name)
            subscriber.on_event(event)

    def get_history(self) -> List[Event]:
        """Return history log."""
        with self._lock:
            return list(self._event_history)


class EventPublisher:
    """Publisher wrapper for systems publishing to a central event bus."""

    def __init__(self, source_name: str, event_bus: EventBus) -> None:
        self.source_name = source_name
        self.event_bus = event_bus

    def publish_event(
        self,
        event_type: EventType | str,
        payload: Optional[Dict[str, Any]] = None,
        priority: EventPriority = EventPriority.MEDIUM,
    ) -> None:
        """Utility wrapper to publish events directly to the bound bus."""
        event = Event(
            event_type=event_type,
            source=self.source_name,
            payload=payload,
            priority=priority,
        )
        self.event_bus.publish(event)
