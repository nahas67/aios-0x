"""Zero-trust bus ACL tests (§24): communities publish ONLY their topics.

Every community receives a ScopedEventBus derived from its declared roster.
Publishing off-roster fails closed. The integration proof: a FULL replay
completes with ZERO acl denials — every real publisher was authorized.
"""

import asyncio
from pathlib import Path

import pytest

from core.event_bus import InMemoryEventBus, ScopedEventBus
from core.persistence import SqliteMemoryStore
from schemas.contracts import PredictionRecord  # noqa: F401 - payload stub below
from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner


def _make(inner: InMemoryEventBus, actor: str, *topics) -> ScopedEventBus:

    return ScopedEventBus(inner, actor, frozenset(topics))


# ------------------------------------------------------------------ unit


def test_publish_outside_ownership_fails_closed() -> None:
    from core.event_bus import EventTopic

    bus = _make(InMemoryEventBus(), "c2-research", EventTopic.HYPOTHESIS_GENERATED)

    async def _flow() -> None:
        await bus.start()
        with pytest.raises(PermissionError, match="may not publish"):
            await bus.publish(EventTopic.ORDER_FILLED, _stub())
        assert bus.denied == ["aios.c5.order_filled"]
        # allowed topic passes through untouched
        seen: list[str] = []

        async def sink(payload) -> None:
            seen.append("hit")

        await bus.subscribe(EventTopic.HYPOTHESIS_GENERATED, sink)
        await bus.publish(EventTopic.HYPOTHESIS_GENERATED, _stub())
        await bus.wait_until_idle()
        await bus.stop()
        assert seen == ["hit"]

    asyncio.run(_flow())


class _StubPayload:
    pass


def _stub():
    from pydantic import BaseModel

    class P(BaseModel):
        x: int = 1

    return P()


def test_listening_is_not_authority() -> None:
    """Subscribing to any topic is unrestricted; publishing is governed."""
    from core.event_bus import EventTopic

    inner = InMemoryEventBus()
    bus = _make(inner, "c7-memory", EventTopic.MEMORY_STORED)
    assert bus._allowed != frozenset(EventTopic)  # scoped for publish only


# ------------------------------------------------- full-replay integration


@pytest.fixture()
def ran(tmp_path: Path) -> ReplayRunner:
    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=120)
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "acl.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
    )
    summary = asyncio.run(runner.run())
    runner._summary = summary  # type: ignore[attr-defined]
    return runner


def test_full_replay_has_zero_acl_denials(ran: ReplayRunner) -> None:
    assert ran._summary.trades_closed >= 1  # type: ignore[attr-defined]
    assert ran.acl_denials == [], (
        f"off-roster publishes detected: {ran.acl_denials}"
    )


def test_every_community_got_a_scoped_bus(ran: ReplayRunner) -> None:
    actors = {scoped.actor_id for scoped in ran._scoped_buses}
    expected = {
        "c1-data-fabric",
        "c2-research",
        "c3-verification",
        "c4-strategy",
        "c5-execution",
        "c6-observation",
        "c7-memory",
        "c8-evolution",
        "c9-governor",
        "c10-world",
        "c11-finance",
        "risk-governor",
    }
    assert expected <= actors


def test_scope_map_matches_declared_roster(ran: ReplayRunner) -> None:
    """Audit roster (persisted) and runtime scopes must agree."""
    store = SqliteMemoryStore(ran.store.db_path)
    roster_events = store.iter_event_payloads("AGENT_REGISTERED")
    assert roster_events, "roster registrations must be audited"
    declared = {e["agent_id"]: set(e.get("publishes", [])) for e in roster_events}
    from core.event_bus import EventTopic
    from simulation.replay_runner import _COMPONENT_BUS_SCOPES

    for actor_id, topics in _COMPONENT_BUS_SCOPES.items():
        declared_topics = declared.get(actor_id, set())
        assert {t.value for t in topics} == declared_topics, (
            f"{actor_id}: runtime scope diverges from declared roster"
        )
    _ = EventTopic
