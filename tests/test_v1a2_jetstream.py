"""V1-A.2 event backbone: JetStream integration + hermetic delivery policy.

The hermetic half (delivery policy, envelope codec, misuse guards) always runs.
The live half needs a JetStream server:

    docker run --rm -p 4222:4222 nats:2-alpine --jetstream
    export AIOS_TEST_NATS_URL="nats://127.0.0.1:4222"

Without ``AIOS_TEST_NATS_URL`` the live tests skip, exactly like the established
``AIOS_TEST_PG_DSN`` pattern, so the default suite stays hermetic.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from communities.c5_execution.oms import DurableOrderManager
from core.financial_kernel import (
    CashPosting,
    Fill,
    OutboxEvent,
    OutboxPublisher,
    OutboxStatus,
    SqliteFinancialStore,
    publish_outbox_event,
)
from core.jetstream_bus import (
    AsyncOutboxPublisher,
    ConsumerAction,
    DurableInboxConsumer,
    JetStreamBus,
    JetStreamOutboxSink,
    is_publishable,
    plan_action,
)
from schemas.contracts import OrderSide

NATS_URL = os.environ.get("AIOS_TEST_NATS_URL", "")
live = pytest.mark.skipif(
    not NATS_URL, reason="set AIOS_TEST_NATS_URL to run the live JetStream tests"
)
pytestmark = pytest.mark.integration


def _seed_order(store: SqliteFinancialStore, client_order_id: str) -> None:
    """Create one committed state change, which also enqueues an outbox event."""
    DurableOrderManager(store).prepare_order(
        client_order_id=client_order_id,
        strategy_id="s1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=1.0,
    )


async def _reset_streams(stream: str = "AIOS_EVENTS", dlq: str = "AIOS_DLQ") -> None:
    """Drop the canonical streams so each live test starts from real boot state.

    The tests reuse the production stream names on purpose: a per-test stream
    name would not overlap-test the subject namespace that actually ships. The
    container is disposable, so deleting the streams between tests is safe.
    """
    import nats

    nc = await nats.connect(NATS_URL, connect_timeout=5, max_reconnect_attempts=0)
    try:
        js = nc.jetstream()
        for name in (dlq, stream):
            try:
                await js.delete_stream(name)
            except Exception:  # noqa: BLE001 - absent is the normal first case
                pass
    finally:
        await nc.close()


@pytest.fixture(autouse=True)
def _fresh_streams() -> object:
    if not NATS_URL:
        yield
        return
    asyncio.run(_reset_streams())
    yield
    asyncio.run(_reset_streams())


# ------------------------------------------------------------ hermetic policy


def test_duplicate_delivery_is_acknowledged_without_reapplying() -> None:
    assert plan_action(1, already_applied=True, max_deliver=5) is ConsumerAction.ACK_DUPLICATE
    assert plan_action(5, already_applied=True, max_deliver=5) is ConsumerAction.ACK_DUPLICATE


def test_new_delivery_is_applied() -> None:
    assert plan_action(1, already_applied=False, max_deliver=5) is ConsumerAction.APPLY


def test_exhausted_delivery_is_dead_lettered() -> None:
    assert plan_action(5, already_applied=False, max_deliver=5) is ConsumerAction.DEAD_LETTER
    assert plan_action(6, already_applied=False, max_deliver=5) is ConsumerAction.DEAD_LETTER


def test_publishable_status() -> None:
    pending = OutboxEvent(event_type="x", producer="p", idempotency_key="k")
    assert is_publishable(pending) is True
    assert is_publishable(pending.model_copy(update={"status": OutboxStatus.PUBLISHED})) is False


def test_sink_rejects_being_driven_from_the_bus_own_loop() -> None:
    """A synchronous sink blocking its own loop would deadlock; say so instead."""

    async def scenario() -> str:
        bus = JetStreamBus("nats://127.0.0.1:1", connect_timeout=0.1)
        bus._loop = asyncio.get_running_loop()
        event = OutboxEvent(event_type="x", producer="p", idempotency_key="k")
        with pytest.raises(RuntimeError) as excinfo:
            JetStreamOutboxSink(bus)(event)
        return str(excinfo.value)

    message = asyncio.run(scenario())
    assert "deadlock" in message
    assert "AsyncOutboxPublisher" in message


def test_outbox_failure_marks_event_retryable_not_dropped(tmp_path: Path) -> None:
    store = SqliteFinancialStore(tmp_path / "f.db")
    try:
        store.post_cash(
            [
                CashPosting(transaction_id="t", account_id="a", amount_minor=100),
                CashPosting(transaction_id="t", account_id="b", amount_minor=-100),
            ]
        )
        _seed_order(store, "retry-1")

        def exploding_sink(_event: OutboxEvent) -> None:
            raise RuntimeError("broker unreachable")

        publisher = OutboxPublisher(store, exploding_sink, retry_delay_seconds=0)
        published, failed = publisher.drain()
        assert (published, failed) == (0, 1)
        # The event is still in the outbox, retryable — nothing was lost.
        assert store.outbox_backlog() == 1
        assert store.dead_letters() == []

        # And a later successful drain publishes the same committed event.
        seen: list[str] = []
        assert publish_outbox_event(store, store.outbox_pending()[0], seen.append) is True
        assert len(seen) == 1
        assert store.outbox_backlog() == 0
    finally:
        store.close()


def test_orphaned_claims_are_recovered_on_restart(tmp_path: Path) -> None:
    db = tmp_path / "f.db"
    store = SqliteFinancialStore(db)
    store.post_cash(
        [
            CashPosting(transaction_id="t", account_id="a", amount_minor=100),
            CashPosting(transaction_id="t", account_id="b", amount_minor=-100),
        ]
    )
    _seed_order(store, "orphan-1")
    # Simulate a publisher that claimed work and then died before publishing.
    claimed = store.claim_outbox("worker-1", limit=10)
    assert claimed
    assert store.dead_letters() == []
    store.close()

    reopened = SqliteFinancialStore(db)
    try:
        recovered = reopened.recover_claims_after_restart()
        assert recovered == len(claimed)
        assert reopened.outbox_backlog() == len(claimed)
        assert all(e.claimed_by is None for e in reopened.outbox_pending())
    finally:
        reopened.close()


# ------------------------------------------------------------------- live bus


@live
class TestJetStreamLive:
    def _bus(self) -> JetStreamBus:
        return JetStreamBus(NATS_URL)

    def test_health_reports_broker_identity(self) -> None:
        async def scenario() -> dict:
            bus = self._bus()
            await bus.connect()
            try:
                return bus.health()
            finally:
                await bus.stop()

        health = asyncio.run(scenario())
        assert health["backend"] == "jetstream"
        assert health["connected"] is True
        assert health["server"]

    def test_financial_transaction_commits_before_publication(self, tmp_path: Path) -> None:
        """The outbox row exists in the committed DB even if the broker is down."""
        store = SqliteFinancialStore(tmp_path / "f.db")
        try:
            _seed_order(store, "live-1")
            # No broker at all: state is committed, the event is pending.
            assert store.outbox_backlog() == 1
            assert store.open_orders()[0].client_order_id == "live-1"
        finally:
            store.close()

    def test_outbox_to_jetstream_to_durable_consumer(self, tmp_path: Path) -> None:
        async def scenario() -> dict:
            bus = self._bus()
            await bus.connect()
            store = SqliteFinancialStore(tmp_path / "f.db")
            effects: list[dict] = []
            try:
                _seed_order(store, "live-2")
                publisher = AsyncOutboxPublisher(store, bus, retry_delay_seconds=0)
                published, failed = await publisher.drain()
                assert (published, failed) == (1, 0)
                assert store.outbox_backlog() == 0

                def effect(payload: dict) -> dict:
                    effects.append(payload)
                    return {"applied": payload.get("object_id")}

                consumer = DurableInboxConsumer(
                    bus,
                    store,
                    "orders-consumer",
                    "aios.platform.order_requested",
                    effect,
                )
                subscription = await bus.pull_subscribe(
                    "aios.platform.order_requested", "orders-consumer"
                )
                await consumer.consume_once(subscription)
                lag = await bus.consumer_lag("orders-consumer")

                # Redelivery must not re-apply: the inbox is the authority.
                second = await bus.pull_subscribe(
                    "aios.platform.order_requested", "orders-consumer"
                )
                before = len(effects)
                await consumer.consume_once(second)
                return {
                    "effects": len(effects),
                    "effects_before_redelivery": before,
                    "inbox": store.inbox_count("orders-consumer"),
                    "lag": lag,
                    "stats": consumer.stats(),
                }
            finally:
                store.close()
                await bus.stop()

        result = asyncio.run(scenario())
        assert result["effects"] == 1
        assert result["effects_before_redelivery"] == 1
        assert result["inbox"] == 1
        assert result["lag"] == 0
        assert result["stats"]["processed"] == 1

    def test_duplicate_payload_is_discarded_by_the_stream(self) -> None:
        """Publishing the same deterministic id twice is deduplicated broker-side."""

        async def scenario() -> tuple[int, int]:
            bus = self._bus()
            await bus.connect()
            try:
                event = OutboxEvent(
                    event_type="aios.platform.order_requested",
                    producer="p",
                    idempotency_key="stable-key-1",
                    payload={"object_id": "obj-1"},
                )
                await bus.publish_envelope(event)
                await bus.publish_envelope(event)
                info = await bus._js.stream_info(bus.stream)
                return bus.published, int(info.state.messages)
            finally:
                await bus.stop()

        published, stored = asyncio.run(scenario())
        assert published == 2  # two successful publish calls...
        assert stored == 1  # ...one stored message (Nats-Msg-Id dedup)

    def test_broker_outage_preserves_committed_state_then_resumes(self, tmp_path: Path) -> None:
        async def scenario() -> dict:
            store = SqliteFinancialStore(tmp_path / "f.db")
            healthy = self._bus()
            await healthy.connect()
            try:
                oms = DurableOrderManager(store)
                order = oms.prepare_order(
                    client_order_id="live-3",
                    strategy_id="s1",
                    symbol="BTC/USD",
                    side=OrderSide.BUY,
                    quantity=1.0,
                )
                oms.accept(order.internal_order_id)
                store.apply_fill(
                    Fill(
                        fill_id="fill-outage",
                        order_id=order.internal_order_id,
                        broker_execution_id="exec-outage",
                        symbol="BTC/USD",
                        side=OrderSide.BUY,
                        quantity=1.0,
                        price=100.0,
                    )
                )

                # Broker down: every publication fails, and NOTHING is lost — a
                # failed publish is recorded as retryable, never dropped.
                down = JetStreamBus("nats://127.0.0.1:59999", connect_timeout=0.3)
                outage = AsyncOutboxPublisher(store, down, retry_delay_seconds=0)
                outage_published, outage_failed = await outage.drain()
                backlog_during_outage = store.outbox_backlog()
                fills_during_outage = len(store.fills())
                assert outage_published == 0
                assert outage_failed >= 1
                assert store.dead_letters() == []

                # Broker back: everything drains, invariants still hold.
                recovered = AsyncOutboxPublisher(store, healthy, retry_delay_seconds=0)
                published, failed = await recovered.drain()
                return {
                    "backlog_during_outage": backlog_during_outage,
                    "fills_during_outage": fills_during_outage,
                    "published_after": published,
                    "failed_after": failed,
                    "backlog_after": store.outbox_backlog(),
                    "invariants_ok": store.verify_invariants().ok,
                }
            finally:
                store.close()
                await healthy.stop()

        result = asyncio.run(scenario())
        assert result["backlog_during_outage"] >= 1
        assert result["fills_during_outage"] == 1
        assert result["published_after"] >= 1
        assert result["backlog_after"] == 0
        assert result["invariants_ok"] is True

    def test_replay_reads_retained_events_without_disturbing_live_position(self) -> None:
        async def scenario() -> tuple[int, int]:
            bus = self._bus()
            await bus.connect()
            try:
                for index in range(3):
                    await bus.publish_envelope(
                        OutboxEvent(
                            event_type="aios.platform.hypothesis_created",
                            producer="p",
                            idempotency_key=f"replay-{index}",
                            payload={"object_id": f"h-{index}"},
                        )
                    )
                replayed: list[dict] = []
                count = await bus.replay(
                    "aios.platform.hypothesis_created",
                    "analysis-replay",
                    replayed.append,
                )
                return count, len(replayed)
            finally:
                await bus.stop()

        count, seen = asyncio.run(scenario())
        assert count == 3
        assert seen == 3
