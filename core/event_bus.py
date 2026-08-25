"""Event bus abstraction and in-memory implementation for AIOS inter-community events."""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable
from enum import StrEnum

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EventTopic(StrEnum):
    """Canonical inter-community event topics.

    Wire values follow the Doc 14 / ADR-002 namespace convention
    ``aios.<community>.<event>``. Member names are stable API; values are canonical.
    """

    DATA_ACQUIRED = "aios.c1.data_acquired"
    DATA_ANOMALY = "aios.c1.data_anomaly"
    EVENT_DETECTED = "aios.c10.event_detected"
    EXPECTATION_UPDATED = "aios.c10.expectation_updated"
    SCENARIOS_PUBLISHED = "aios.c10.scenarios_published"
    REGIME_CHANGED = "aios.c10.regime_changed"
    HYPOTHESIS_GENERATED = "aios.c2.hypothesis_generated"
    VERIFICATION_COMPLETED = "aios.c3.verification_completed"
    STRATEGY_GENERATED = "aios.c4.strategy_generated"
    OPPORTUNITY_RANKED = "aios.c4.opportunity_ranked"
    PORTFOLIO_ALLOCATED = "aios.c9.portfolio_allocated"
    PORTFOLIO_REJECTED = "aios.c9.portfolio_rejected"
    ORDER_SUBMITTED = "aios.c5.order_submitted"
    ORDER_FILLED = "aios.c5.order_filled"
    RECONCILIATION_FAILED = "aios.c5.reconciliation_failed"
    RISK_EMERGENCY = "aios.risk.emergency"
    LEDGER_POSTED = "aios.c11.ledger_posted"
    COMPLIANCE_ALERT = "aios.c11.compliance_alert"
    TRADE_EXECUTED = "aios.c5.order_executed"  # alias: order_executed semantics
    OBSERVATION_COMPLETED = "aios.c6.observation_completed"
    MEMORY_STORED = "aios.c7.memory_stored"
    EVOLUTION_TRIGGERED = "aios.c8.evolution_triggered"

    # ---- Platform lifecycle events (Phase D, original architecture §18).
    # Emitted by the kernel bridge; consumed by control/audit/memory planes.
    PLATFORM_DATASET_VERSION_CREATED = "aios.platform.dataset_version_created"
    PLATFORM_EXPERIMENT_STARTED = "aios.platform.experiment_started"
    PLATFORM_EXPERIMENT_COMPLETED = "aios.platform.experiment_completed"
    PLATFORM_HYPOTHESIS_CREATED = "aios.platform.hypothesis_created"
    PLATFORM_HYPOTHESIS_REJECTED = "aios.platform.hypothesis_rejected"
    PLATFORM_EVALUATION_COMPLETED = "aios.platform.evaluation_completed"
    PLATFORM_ORDER_REQUESTED = "aios.platform.order_requested"
    PLATFORM_ORDER_AUTHORIZED = "aios.platform.order_authorized"
    PLATFORM_ORDER_DENIED = "aios.platform.order_denied"
    PLATFORM_RISK_DECISION_MADE = "aios.platform.risk_decision_made"
    PLATFORM_EXECUTION_COMPLETED = "aios.platform.execution_completed"
    PLATFORM_POST_MORTEM_CREATED = "aios.platform.post_mortem_created"


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

    async def wait_until_idle(self) -> None:
        """Block until queued events are processed. No-op for always-live buses."""
        return None


class InMemoryEventBus(BaseEventBus):
    """In-memory event bus implementation using asyncio.Queue and background workers."""

    def __init__(self, queue_maxsize: int = 0) -> None:
        """Initialize the in-memory event bus."""
        self._subscribers: dict[EventTopic, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[tuple[EventTopic, BaseModel]] = asyncio.Queue(
            maxsize=queue_maxsize
        )
        self._worker_task: asyncio.Task[None] | None = None
        self._running: bool = False

    async def start(self) -> None:
        """Start the background worker task to process events from the queue."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(
            self._run_worker(), name="in_memory_event_bus_worker"
        )
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
