"""Event bus abstraction and in-memory implementation for AIOS inter-community events."""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum
from typing import Awaitable, Callable
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EventTopic(str, Enum):
    """Event topics for inter-community communication."""

    DATA_ACQUIRED = "data.acquired"
    HYPOTHESIS_GENERATED = "research.hypothesis_generated"
    VERIFICATION_COMPLETED = "verification.completed"
    STRATEGY_GENERATED = "strategy.generated"
    TRADE_EXECUTED = "trade.executed"
    OBSERVATION_COMPLETED = "observation.completed"
    MEMORY_STORED = "memory.stored"
    EVOLUTION_TRIGGERED = "evolution.triggered"


# Type alias for event handler callbacks
EventHandler = Callable[[BaseModel], Awaitable[None]]


class BaseEventBus(ABC):
    """Abstract base class for event bus implementations."""

    @abstractmethod
    async def publish(self, topic: EventTopic, payload: BaseModel) -> None:
        """Publish a payload to a specific topic."""
        pass

    @abstractmethod
    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        """Subscribe a handler callback to a topic."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the event bus worker tasks."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the event bus worker tasks and clean up resources."""
        pass


class InMemoryEventBus(BaseEventBus):
    """In-memory event bus implementation using asyncio.Queue and background workers."""

    def __init__(self, queue_maxsize: int = 0) -> None:
        """Initialize the in-memory event bus."""
        self._subscribers: dict[EventTopic, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[tuple[EventTopic, BaseModel]] = asyncio.Queue(maxsize=queue_maxsize)
        self._worker_task: asyncio.Task[None] | None = None
        self._running: bool = False

    async def start(self) -> None:
        """Start the background worker task to process events from the queue."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._run_worker(), name="in_memory_event_bus_worker")
        logger.info("InMemoryEventBus started successfully.")

    async def stop(self) -> None:
        """Stop the background worker task and clean up resources."""
        if not self._running:
            return
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("InMemoryEventBus stopped successfully.")

    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        """Register a subscriber callback for a specific event topic."""
        if handler not in self._subscribers[topic]:
            self._subscribers[topic].append(handler)
            logger.debug("Subscribed %s to topic %s", handler, topic)

    async def publish(self, topic: EventTopic, payload: BaseModel) -> None:
        """Publish an event payload to a topic queue."""
        await self._queue.put((topic, payload))
        logger.debug("Published event payload to topic %s", topic)

    async def wait_until_idle(self) -> None:
        """Wait until all current items in the event queue have been processed."""
        await self._queue.join()

    async def _run_worker(self) -> None:
        """Continuously consume and process events from the queue."""
        while self._running:
            try:
                topic, payload = await self._queue.get()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Unexpected error fetching event from queue: %s", exc)
                continue

            try:
                handlers = self._subscribers.get(topic, [])
                for handler in handlers:
                    try:
                        await handler(payload)
                    except Exception as exc:
                        logger.exception(
                            "Unhandled exception in subscriber callback %s for topic %s: %s",
                            handler,
                            topic,
                            exc,
                        )
            finally:
                self._queue.task_done()
