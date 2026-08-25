"""Phase D platform-event tests: the control plane's typed orchestration stream.

Proves that kernel-bridge operations emit canonical ``aios.platform.*`` events
onto the bus, that they are durable in the hash-chained audit log (via the
runner's catch-all logger), and that their counts reconcile with real trading
activity — not just that "some events happened".
"""

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.event_bus import InMemoryEventBus
from core.platform_events import (
    PlatformEvent,
    PlatformEventType,
    order_denied,
    order_requested,
)
from simulation.generate_golden_data import write_dataset
from simulation.kernel_bridge import KernelBridge
from simulation.replay_runner import ReplayRunner


@pytest.fixture()
def small_dataset(tmp_path: Path) -> dict[str, Path]:
    write_dataset(tmp_path / "golden", symbols=["BTC/USD", "ETH/USD"], total_bars=120)
    by_symbol = {
        "BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv",
        "ETH/USD": tmp_path / "golden" / "ETH_USD_1d.csv",
    }
    return {s: p for s, p in by_symbol.items() if p.exists()}


def _run(dataset: dict[str, Path], store_path: Path) -> tuple[ReplayRunner, object]:
    runner = ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=store_path,
        initial_balance=100000.0,
        slippage_pct=0.05,
    )
    summary = asyncio.run(runner.run())
    return runner, summary


# ------------------------------------------------------------------- model


def test_wire_names_follow_adr002_namespace() -> None:
    for member in PlatformEventType:
        assert member.value.startswith("aios.platform.")
        assert " " not in member.value


def test_platform_event_requires_core_fields() -> None:
    with pytest.raises(ValidationError):
        PlatformEvent(event_type=PlatformEventType.ORDER_REQUESTED)  # no actor/object
    event = order_requested("plan-1", "strat-1", "BUY", "SPY")
    assert event.actor_id == "c5-execution"
    assert event.object_id == "strat-1"
    assert event.metadata["action"] == "BUY"


def test_order_denied_carries_receipt_ids() -> None:
    event = order_denied("strat-x", "exposure cap", ["rcpt-9"])
    assert event.receipt_ids == ["rcpt-9"]
    assert event.actor_id == "kernel.authority"
    governor = order_denied("strat-y", "cap", ["rcpt-2"], source="c9-governor")
    assert governor.actor_id == "c9-governor"


# ------------------------------------------------------------- full replay


def test_full_replay_emits_expected_platform_kinds(small_dataset, tmp_path) -> None:
    runner, summary = _run(small_dataset, tmp_path / "k.db")
    store = runner.store

    expected = {
        "aios.platform.dataset_version_created",
        "aios.platform.experiment_started",
        "aios.platform.experiment_completed",
        "aios.platform.hypothesis_created",
        "aios.platform.order_requested",
        "aios.platform.order_authorized",
        "aios.platform.execution_completed",
        "aios.platform.evaluation_completed",
        "aios.platform.post_mortem_created",
    }
    for kind in expected:
        payloads = store.iter_event_payloads(kind)
        assert payloads, f"no platform events of kind {kind}"
        sample = payloads[0]
        for field in ("event_type", "actor_id", "object_type", "object_id", "occurred_at"):
            assert field in sample

    # counts reconcile with trading reality
    postmortems = store.iter_event_payloads("aios.platform.post_mortem_created")
    assert len(postmortems) == summary.trades_closed
    executions = store.iter_event_payloads("aios.platform.execution_completed")
    assert len(executions) == summary.trades_closed
    authorized = store.iter_event_payloads("aios.platform.order_authorized")
    assert len(authorized) >= summary.trades_closed  # every fill was authorized

    started = store.iter_event_payloads("aios.platform.experiment_started")[0]
    completed = store.iter_event_payloads("aios.platform.experiment_completed")[0]
    assert started["object_id"] == runner.kernel_bridge.experiment_id
    assert completed["object_id"] == runner.kernel_bridge.experiment_id
    assert completed["metadata"]["trades_closed"] == summary.trades_closed


def test_hypothesis_rejected_events_match_negative_knowledge(small_dataset, tmp_path) -> None:
    runner, _summary = _run(small_dataset, tmp_path / "k.db")
    rejected_events = runner.store.iter_event_payloads("aios.platform.hypothesis_rejected")
    rejected_states = sum(
        1
        for hid in runner.kernel_bridge.tracked_hypothesis_ids()
        if runner.kernel_bridge.kernel.state_machine.get_state("hypothesis", hid) == "REJECTED"
    )
    # every kernel REJECTED hypothesis produced exactly one platform rejection event
    assert len(rejected_events) == rejected_states
    for payload in rejected_events:
        assert "realized_pnl" in payload["metadata"]


def test_platform_events_durable_across_reopen(small_dataset, tmp_path) -> None:
    """Events live in the hash-chained log: readable from a fresh store handle."""
    dataset = small_dataset
    db = tmp_path / "durable.db"
    runner, _summary = _run(dataset, db)
    experiment_id = str(runner.kernel_bridge.experiment_id)

    reopened = type(runner.store)(db)  # fresh handle over the same file
    started = reopened.iter_event_payloads("aios.platform.experiment_started")
    assert any(p["object_id"] == experiment_id for p in started)
    ok, bad = reopened.verify_chain()
    assert ok and bad is None
    reopened.close()


# ------------------------------------------------------------ subscriptions


def test_consumer_can_subscribe_to_platform_topics(small_dataset, tmp_path) -> None:
    """A control-plane-style consumer receives typed events during a run."""
    received: list[str] = []
    bus = InMemoryEventBus()

    async def _consumer(event: object) -> None:
        received.append(event.event_type.value)  # type: ignore[attr-defined]

    async def _flow() -> None:
        await bus.start()
        from core.event_bus import EventTopic

        await bus.subscribe(EventTopic.PLATFORM_ORDER_AUTHORIZED, _consumer)
        runner = ReplayRunner(
            csv_path_by_symbol=small_dataset,
            store_path=tmp_path / "sub.db",
            initial_balance=100000.0,
            slippage_pct=0.05,
            bus=bus,
        )
        await runner.run()
        await bus.stop()

    asyncio.run(_flow())
    assert received, "consumer saw no ORDER_AUTHORIZED events"


# ------------------------------------------------------------------ denials


def test_governor_denial_emits_risk_and_order_denied() -> None:
    from core.event_bus import EventTopic

    received: list[PlatformEventType] = []
    bus = InMemoryEventBus()

    async def _consumer(event: PlatformEvent) -> None:
        received.append(event.event_type)

    async def _flow() -> None:
        await bus.start()
        await bus.subscribe(EventTopic.PLATFORM_ORDER_DENIED, _consumer)
        await bus.subscribe(EventTopic.PLATFORM_RISK_DECISION_MADE, _consumer)
        bridge = KernelBridge(event_bus=bus)
        await bridge.on_plan_denied("strat-deny-1", "exposure cap exceeded")
        await bus.wait_until_idle()
        await bus.stop()

    asyncio.run(_flow())
    assert set(received) == {
        PlatformEventType.ORDER_DENIED,
        PlatformEventType.RISK_DECISION_MADE,
    }
