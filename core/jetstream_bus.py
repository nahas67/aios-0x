"""NATS JetStream: the production event backbone (master-spec §29–§31).

``InMemoryEventBus`` remains for hermetic unit tests and local simulation. This
module is what production runs on:

- **Durable streams.** One stream per retention class, with subjects under the
  canonical ``aios.>`` namespace and a duplicate window keyed on the outbox
  envelope's deterministic ``idempotency_key``.
- **Durable pull consumers** with explicit acks, ``ack_wait`` redelivery, a
  bounded ``max_deliver``, and dead-letter routing for poison messages.
- **Replay** through ``fetch``/``DeliverPolicy`` without touching live state.
- **Backpressure** by construction: a pull consumer fetches only what it can
  apply; there is no unbounded in-process queue.
- **Reconnection** delegated to nats-py (``max_reconnect_attempts=-1``) plus a
  health surface that reports honestly when the broker is unreachable.

The outbox hand-off is :class:`JetStreamOutboxSink`: a synchronous callable that
``OutboxPublisher`` can drive, publishing the *committed* envelope. Because the
financial transaction has already committed before the sink runs, a broker outage
can only delay publication — it can never lose or duplicate economic state. A
failed publish leaves the row ``PENDING`` with exponential backoff, so
publication resumes when the broker returns.

Exactly-once *effects* are not JetStream's job: the broker gives at-least-once
delivery, and :class:`DurableInboxConsumer` makes the application side idempotent
by recording ``(consumer, event_id)`` in the durable inbox inside the same
database transaction as the effect it describes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from core.event_bus import BaseEventBus, EventHandler, EventTopic
from core.financial_kernel import BaseFinancialStore, OutboxEvent, OutboxStatus
from core.platform_events import PlatformEvent
from schemas.contracts import generate_uuid

logger = logging.getLogger(__name__)

DEFAULT_URL = "nats://127.0.0.1:4222"
DEFAULT_STREAM = "AIOS_EVENTS"
DEFAULT_SUBJECT_ROOT = "aios"
#: The DLQ root deliberately sits OUTSIDE the ``aios.>`` primary namespace:
#: JetStream rejects overlapping stream subjects, so a dead-letter stream under
#: ``aios.dlq.>`` could never coexist with the primary ``aios.>`` stream.
DEFAULT_DLQ_STREAM = "AIOS_DLQ"
DEFAULT_DLQ_ROOT = "dlq.aios"
#: One hour of broker-side deduplication on the deterministic idempotency key.
DEFAULT_DUPLICATE_WINDOW_SECONDS = 3600
DEFAULT_MAX_DELIVER = 5
DEFAULT_ACK_WAIT_SECONDS = 30.0


def _require_nats() -> Any:
    """Import nats-py lazily so unit tests need no optional dependency."""
    try:
        import nats
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise RuntimeError(
            "JetStream support requires the optional dependency: pip install 'aios[nats]'"
        ) from exc
    return nats


class ConsumerAction(StrEnum):
    """What a consumer should do with one delivery."""

    APPLY = "APPLY"
    ACK_DUPLICATE = "ACK_DUPLICATE"
    DEAD_LETTER = "DEAD_LETTER"


def plan_action(num_delivered: int, already_applied: bool, max_deliver: int) -> ConsumerAction:
    """Pure delivery policy, so the crash/redelivery rules are unit-testable.

    A duplicate is acknowledged without re-applying. A delivery that has already
    exhausted its budget is dead-lettered rather than retried forever, which is
    what keeps a poison message from starving the consumer group.
    """
    if already_applied:
        return ConsumerAction.ACK_DUPLICATE
    if num_delivered >= max_deliver:
        return ConsumerAction.DEAD_LETTER
    return ConsumerAction.APPLY


class JetStreamBus(BaseEventBus):
    """Durable publish/subscribe and outbox publication over JetStream."""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        *,
        stream: str = DEFAULT_STREAM,
        subject_root: str = DEFAULT_SUBJECT_ROOT,
        dlq_stream: str = DEFAULT_DLQ_STREAM,
        dlq_root: str = DEFAULT_DLQ_ROOT,
        # Kept explicit so an operator sees why the DLQ namespace differs.
        duplicate_window_seconds: int = DEFAULT_DUPLICATE_WINDOW_SECONDS,
        max_deliver: int = DEFAULT_MAX_DELIVER,
        ack_wait_seconds: float = DEFAULT_ACK_WAIT_SECONDS,
        publish_attempts: int = 3,
        publish_retry_delay: float = 0.25,
        publish_timeout: float = 5.0,
        connect_timeout: float = 5.0,
    ) -> None:
        self.url = url
        self.stream = stream
        self.subject_root = subject_root
        self.dlq_stream = dlq_stream
        self.dlq_root = dlq_root
        self.duplicate_window_seconds = duplicate_window_seconds
        self.max_deliver = max_deliver
        self.ack_wait_seconds = ack_wait_seconds
        self.publish_attempts = publish_attempts
        self.publish_retry_delay = publish_retry_delay
        # An ACK that never arrives is indistinguishable from a publish that was
        # never sent, so it is retried — safely, because the retry carries the
        # same ``Nats-Msg-Id`` and is discarded by the stream's duplicate window.
        self.publish_timeout = publish_timeout
        self.connect_timeout = connect_timeout
        self._nc: Any = None
        self._js: Any = None
        self._handlers: dict[EventTopic, list[EventHandler]] = {}
        self._subscriptions: list[Any] = []
        self._pull_tasks: list[asyncio.Task[None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self.publish_failures: int = 0
        self.published: int = 0
        self.deduplicated: int = 0

    # ------------------------------------------------------------- lifecycle

    async def connect(self) -> None:
        nats = _require_nats()
        self._loop = asyncio.get_running_loop()
        self._nc = await nats.connect(
            self.url,
            connect_timeout=self.connect_timeout,
            max_reconnect_attempts=-1,  # reconnection is mandatory, not best-effort
            reconnect_time_wait=1.0,
            error_cb=self._on_error,
            disconnected_cb=self._on_disconnected,
            reconnected_cb=self._on_reconnected,
        )
        self._js = self._nc.jetstream()
        await self._ensure_streams()

    async def _ensure_streams(self) -> None:
        await self._js.add_stream(
            name=self.stream,
            subjects=[f"{self.subject_root}.>"],
            duplicate_window=self.duplicate_window_seconds,
        )
        await self._js.add_stream(
            name=self.dlq_stream,
            subjects=[f"{self.dlq_root}.>"],
            duplicate_window=self.duplicate_window_seconds,
        )

    async def _on_error(self, exc: Exception) -> None:
        logger.warning("JetStream async error: %s", exc)

    async def _on_disconnected(self) -> None:
        logger.warning("JetStream disconnected; committed events stay in the outbox")

    async def _on_reconnected(self) -> None:
        logger.warning("JetStream reconnected; resuming outbox publication")

    async def start(self) -> None:
        if self._nc is None:
            await self.connect()

    async def stop(self) -> None:
        for task in self._pull_tasks:
            task.cancel()
        for task in self._pull_tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown
                pass
        self._pull_tasks.clear()
        self._subscriptions.clear()
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None
            self._js = None

    # -------------------------------------------------------------- publish

    async def publish(self, topic: EventTopic, payload: BaseModel) -> None:
        """Publish a platform invocation, deduplicated on its deterministic content."""
        if self._js is None:
            raise RuntimeError("JetStreamBus.publish called before connect()")
        body = payload.model_dump_json().encode()
        event_id = getattr(payload, "object_id", None) or hashlib.sha256(body).hexdigest()
        await self._publish(str(topic), body, str(event_id))

    async def publish_envelope(self, event: OutboxEvent) -> None:
        """Publish one committed outbox envelope (the ``OutboxPublisher`` sink)."""
        await self._publish(
            event.event_type,
            event.model_dump_json().encode(),
            event.idempotency_key,
        )

    async def _publish(self, subject: str, body: bytes, msg_id: str) -> None:
        """Publish with bounded retry.

        ``Nats-Msg-Id`` lets JetStream discard a duplicate within the stream's
        duplicate window, so a retry after a lost ACK cannot double-publish.
        """
        if self._js is None:
            raise RuntimeError("JetStreamBus is not connected")
        wire_subject = subject if subject.startswith(f"{self.subject_root}.") else (
            f"{self.subject_root}.{subject}"
        )
        last_error: Exception | None = None
        for attempt in range(1, self.publish_attempts + 1):
            try:
                ack = await self._js.publish(
                    wire_subject,
                    body,
                    headers={"Nats-Msg-Id": msg_id},
                    timeout=self.publish_timeout,
                )
                self.published += 1
                logger.debug("published %s seq=%s duplicate=%s", wire_subject, ack.seq, ack.duplicate)
                return
            except Exception as exc:  # noqa: BLE001 - retry then surface
                last_error = exc
                self.publish_failures += 1
                logger.warning(
                    "JetStream publish attempt %d/%d failed for %s: %s",
                    attempt,
                    self.publish_attempts,
                    wire_subject,
                    exc,
                )
                if attempt < self.publish_attempts:
                    await asyncio.sleep(self.publish_retry_delay * attempt)
        raise RuntimeError(f"JetStream publish failed after {self.publish_attempts} attempts") from last_error

    # ------------------------------------------------------------ subscribe

    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        """Push subscription for platform events (fan-out, no inbox required)."""
        if self._js is None:
            raise RuntimeError("JetStreamBus.subscribe called before connect()")
        self._handlers.setdefault(topic, []).append(handler)
        subscription = await self._js.subscribe(
            f"{self.subject_root}.{topic}",
            cb=self._dispatch(str(topic)),
            durable=None,
        )
        self._subscriptions.append(subscription)

    def _dispatch(self, topic: str) -> Callable[[Any], Awaitable[None]]:
        async def _handle(msg: Any) -> None:
            try:
                payload = _decode_platform_payload(topic, _decode_envelope(msg.data))
            except Exception:  # noqa: BLE001 - a bad payload must not kill the worker
                logger.exception("undecodable platform event on %s; dead-lettering", topic)
                await self.dead_letter(topic, {}, "undecodable payload")
                await msg.term()
                return
            for handler in self._handlers.get(EventTopic(topic), []):
                await handler(payload)
            await msg.ack()

        return _handle

    # ------------------------------------------------------------- consumers

    async def pull_subscribe(
        self,
        subject: str,
        durable: str,
        *,
        stream: str | None = None,
    ) -> Any:
        """Create (or reattach to) a durable pull consumer.

        Returns the ``nats-py`` subscription object. It is typed ``Any`` on
        purpose: ``nats-py`` is an optional dependency, so the concrete type is
        not importable in an install without the ``aios[nats]`` extra.
        """
        nats = _require_nats()
        if self._js is None:
            raise RuntimeError("JetStreamBus.pull_subscribe called before connect()")
        config = nats.js.api.ConsumerConfig(
            durable_name=durable,
            ack_policy=nats.js.api.AckPolicy.EXPLICIT,
            deliver_policy=nats.js.api.DeliverPolicy.ALL,
            max_deliver=self.max_deliver,
            ack_wait=self.ack_wait_seconds,
        )
        return await self._js.pull_subscribe(
            subject, durable=durable, stream=stream or self.stream, config=config
        )

    async def consumer_lag(self, durable: str, stream: str | None = None) -> int | None:
        """Undelivered message count, or ``None`` when it cannot be read."""
        if self._js is None:
            return None
        try:
            info = await self._js.consumer_info(stream or self.stream, durable)
            return int(info.num_pending)
        except Exception as exc:  # noqa: BLE001 - unknown lag is not zero lag
            logger.warning("consumer lag unavailable for %s: %s", durable, exc)
            return None

    async def dead_letter(self, event_type: str, payload: dict[str, Any], error: str) -> None:
        """Route a poison message to the DLQ stream with its failure reason."""
        body = json.dumps({"event_type": event_type, "error": error, "payload": payload}).encode()
        await self._publish(
            f"{self.dlq_root}.{event_type}", body, generate_uuid()
        )

    async def replay(
        self,
        subject: str,
        durable: str,
        handler: Callable[[dict[str, Any]], None],
        *,
        batch: int = 100,
        timeout: float = 2.0,
        max_batches: int = 10,
    ) -> int:
        """Re-read retained events through a dedicated replay consumer.

        Replay never acks into the live consumer's position: it uses its own
        durable name so re-running an analysis cannot disturb production
        delivery state.
        """
        subscription = await self.pull_subscribe(subject, durable, stream=self.stream)
        seen = 0
        for _ in range(max_batches):
            try:
                messages = await subscription.fetch(batch, timeout=timeout)
            except Exception:  # noqa: BLE001 - timeout means "no more messages"
                break
            for msg in messages:
                handler(_decode_envelope(msg.data))
                seen += 1
                await msg.ack()
        logger.info("replayed %d event(s) from %s via %s", seen, subject, durable)
        return seen

    def health(self) -> dict[str, Any]:
        """Honest broker health: unknown is reported as unknown, never as OK."""
        connected = self._nc is not None and bool(getattr(self._nc, "is_connected", False))
        reconnects: int | None = None
        if self._nc is not None:  # nats-py raises until the first connect completes
            try:
                reconnects = int(self._nc.stats.get("reconnects", 0))
            except Exception:  # noqa: BLE001 - unknown is not zero
                reconnects = None
        return {
            "backend": "jetstream",
            "url": self.url,
            "stream": self.stream,
            "connected": connected,
            "server": str(getattr(self._nc, "connected_server_version", "") or "") or None,
            "reconnect_count": reconnects,
            "published": self.published,
            "publish_failures": self.publish_failures,
        }


class JetStreamOutboxSink:
    """Synchronous outbox sink that marshals publication onto the bus's loop.

    ``OutboxPublisher`` is synchronous on purpose: it must be drivable from a
    simple scheduler, and a publish failure has to reach it as an exception so the
    event is retried rather than silently dropped.

    The sink therefore **must not** be called from the event loop's own thread: a
    synchronous caller blocking that loop while waiting for a coroutine scheduled
    on it would deadlock. That misuse is detected and reported as an actionable
    error instead of hanging. Event-loop callers should use
    :class:`AsyncOutboxPublisher`, which needs no marshalling at all.
    """

    def __init__(self, bus: JetStreamBus, *, timeout_seconds: float = 10.0) -> None:
        self.bus = bus
        self.timeout_seconds = timeout_seconds

    def __call__(self, event: OutboxEvent) -> None:
        loop = self.bus._loop
        if loop is None or not loop.is_running():
            raise RuntimeError("JetStream bus loop is not running; cannot publish")
        try:
            running: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            raise RuntimeError(
                "JetStreamOutboxSink called from the event loop's own thread, which"
                " would deadlock; use AsyncOutboxPublisher (or run OutboxPublisher"
                " in a worker thread)"
            )
        future = asyncio.run_coroutine_threadsafe(self.bus.publish_envelope(event), loop)
        future.result(timeout=self.timeout_seconds)


class AsyncOutboxPublisher:
    """Outbox drain for event-loop callers (no worker thread, no marshalling).

    Shares :func:`core.financial_kernel.publish_outbox_event` with the synchronous
    publisher, so the claim/retry/backoff/commit semantics are literally the same
    code on both paths.
    """

    def __init__(
        self,
        store: BaseFinancialStore,
        bus: JetStreamBus,
        worker: str = "outbox-publisher",
        *,
        retry_delay_seconds: int = 5,
    ) -> None:
        self.store = store
        self.bus = bus
        self.worker = worker
        self.retry_delay_seconds = retry_delay_seconds

    async def drain(self, limit: int = 100) -> tuple[int, int]:
        """Publish pending events; returns (published, failed)."""
        from core.financial_kernel import record_outbox_failure

        published = 0
        failed = 0
        for event in self.store.claim_outbox(self.worker, limit=limit):
            try:
                await self.bus.publish_envelope(event)
            except Exception as exc:  # noqa: BLE001 - record and retry later
                record_outbox_failure(
                    self.store, event.event_id, exc, self.retry_delay_seconds
                )
                failed += 1
                continue
            self.store.mark_published(event.event_id)
            published += 1
        return published, failed


class DurableInboxConsumer:
    """At-least-once transport made into exactly-once *effects* (§31).

    The order is load-bearing:

    1. receive the delivery,
    2. begin a database transaction,
    3. check the durable inbox for ``(consumer, event_id)``,
    4. if already processed, acknowledge safely and apply nothing,
    5. otherwise run the deterministic effect,
    6. record the inbox result,
    7. commit,
    8. acknowledge the transport.

    Crashing before step 7 rolls the effect and the inbox row back together, so
    redelivery re-applies cleanly. Crashing between 7 and 8 leaves the effect
    applied and unacknowledged; redelivery then hits step 4 and acks without
    re-applying. Both boundaries have tests.
    """

    def __init__(
        self,
        bus: JetStreamBus,
        store: BaseFinancialStore,
        name: str,
        subject: str,
        effect: Callable[[dict[str, Any]], Any],
        *,
        batch: int = 10,
        fetch_timeout: float = 1.0,
        max_deliver: int | None = None,
    ) -> None:
        self.bus = bus
        self.store = store
        self.name = name
        self.subject = subject
        self.effect = effect
        self.batch = batch
        self.fetch_timeout = fetch_timeout
        self.max_deliver = max_deliver or bus.max_deliver
        self.processed = 0
        self.duplicates = 0
        self.dead_lettered = 0

    def process_payload(self, event_id: str, payload: dict[str, Any]) -> str:
        """Apply one event inside a single transaction with its inbox record.

        Returns one of ``APPLIED``, ``DUPLICATE`` or ``FAILED:<error>``. This is
        the unit the crash-boundary tests drive directly.
        """
        already = self.store.was_applied(self.name, event_id)
        if already is not None:
            self.duplicates += 1
            return "DUPLICATE"
        try:
            with self.store.transaction() as tx:
                result = self.effect(payload)
                digest = hashlib.sha256(
                    json.dumps(result, sort_keys=True, default=str).encode()
                ).hexdigest()
                tx.record_applied(self.name, event_id, digest)
        except Exception as exc:  # noqa: BLE001 - surface as a retryable failure
            logger.warning("consumer %s failed on %s: %s", self.name, event_id, exc)
            return f"FAILED:{exc}"
        self.processed += 1
        return "APPLIED"

    async def consume_once(self, subscription: Any) -> int:
        """Fetch and handle one batch; returns the number of messages handled."""
        try:
            messages = await subscription.fetch(self.batch, timeout=self.fetch_timeout)
        except Exception:  # noqa: BLE001 - fetch timeout is the idle path
            return 0
        for msg in messages:
            await self._handle_message(msg)
        return len(messages)

    async def _handle_message(self, msg: Any) -> None:
        envelope = _decode_envelope(msg.data)
        event_id = str(
            envelope.get("event_id")
            or hashlib.sha256(msg.data).hexdigest()
        )
        payload = envelope.get("payload") or envelope
        delivered = int(getattr(getattr(msg, "metadata", None), "num_delivered", 1))
        action = plan_action(
            delivered,
            already_applied=self.store.was_applied(self.name, event_id) is not None,
            max_deliver=self.max_deliver,
        )
        if action is ConsumerAction.ACK_DUPLICATE:
            self.duplicates += 1
            await msg.ack()
            return
        if action is ConsumerAction.DEAD_LETTER:
            self.dead_lettered += 1
            await self.bus.dead_letter(
                str(envelope.get("event_type", self.subject)),
                payload,
                f"exhausted {self.max_deliver} deliveries",
            )
            await msg.term()
            return
        outcome = self.process_payload(event_id, payload)
        if outcome == "DUPLICATE":
            await msg.ack()
            return
        if outcome.startswith("FAILED:"):
            # Redelivery is the retry: a transient failure will succeed later, a
            # permanent one will exhaust max_deliver and be dead-lettered.
            await msg.nak()
            return
        await msg.ack()

    async def run(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Long-running pull loop (until cancelled or ``stop_event`` is set)."""
        subscription = await self.bus.pull_subscribe(self.subject, self.name)
        try:
            while stop_event is None or not stop_event.is_set():
                await self.consume_once(subscription)
                await asyncio.sleep(0)
        finally:
            unsubscribe = getattr(subscription, "unsubscribe", None)
            if unsubscribe is not None:
                await unsubscribe()

    def stats(self) -> dict[str, Any]:
        return {
            "consumer": self.name,
            "subject": self.subject,
            "processed": self.processed,
            "duplicates": self.duplicates,
            "dead_lettered": self.dead_lettered,
            "inbox_rows": self.store.inbox_count(self.name),
        }


# --------------------------------------------------------------------- codec


def _decode_envelope(data: bytes) -> dict[str, Any]:
    """Decode an outbox envelope, tolerating a bare payload for compatibility."""
    try:
        decoded = json.loads(data.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("event payload is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("event payload must be a JSON object")
    return decoded


def _decode_platform_payload(topic: str, raw: dict[str, Any]) -> PlatformEvent:
    """Rebuild a typed ``PlatformEvent`` from a published envelope or payload."""
    body = raw.get("payload") if "payload" in raw and "event_type" in raw else raw
    if isinstance(body, dict) and "event_type" not in body:
        body = {**body, "event_type": raw.get("event_type", topic)}
    return PlatformEvent.model_validate(body)


def is_publishable(event: OutboxEvent) -> bool:
    """Whether the publisher should attempt this event in its current state."""
    return event.status in (OutboxStatus.PENDING, OutboxStatus.PUBLISHING)
