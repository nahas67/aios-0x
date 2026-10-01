"""The regime engine, tested directly.

The goal registry pointed a gate at `tests/test_regime_engine.py` for two
decades of accumulated claims, and that file did not exist. The engine it names
has existed the whole time in `communities/c10_world/regime_engine.py` and was
exercised only incidentally, through tests that import it as a collaborator.
Two of its properties are load-bearing for the constitution and were pinned
nowhere:

  - it refuses to label before it has evidence (five bars), rather than
    emitting a trend computed from three points;
  - it carries `is_simulated` onto every label it produces, which is
    CONSTITUTION.md section 2.5, Honesty Law 1.3, and the reason a simulated
    replay can never be mistaken for a live observation downstream.

The second gate attached to G100 named a per-strategy "domain of competence"
that has never existed. That gate was removed from the registry rather than
satisfied, and the gap is recorded in the goal's notes; architecture section 2
Layer 9 does mandate the capability, so it is owed, but it is not delivered and
a test cannot manufacture it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from communities.c10_world.regime_engine import RegimeEngine, statistics_stdev
from core.event_bus import EventTopic, InMemoryEventBus
from schemas.contracts import (
    MarketDataPayload,
    PriceData,
    RegimeState,
    TrendLabel,
    VolRegime,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _bar(close: float, *, ts: datetime = T0, simulated: bool = True) -> MarketDataPayload:
    return MarketDataPayload(
        timestamp=ts,
        symbol="AAPL",
        timeframe="1d",
        price_data=PriceData(
            open=Decimal(str(close)),
            high=Decimal(str(close)),
            low=Decimal(str(close)),
            close=Decimal(str(close)),
            volume=Decimal("1000"),
        ),
        is_simulated=simulated,
    )


def _engine(bus: InMemoryEventBus | None = None, **kwargs: object) -> RegimeEngine:
    return RegimeEngine(bus or InMemoryEventBus(), **kwargs)  # type: ignore[arg-type]


async def _feed(
    engine: RegimeEngine, closes: list[float], *, simulated: bool = True
) -> list[RegimeState | None]:
    """Feed closes in order, one bar apart."""
    out: list[RegimeState | None] = []
    for i, close in enumerate(closes):
        out.append(
            await engine.on_data_acquired(
                _bar(close, ts=T0 + timedelta(days=i), simulated=simulated)
            )
        )
    return out


# ══════════════════════════════════════════════════════════════════════════
# Refusing to label before there is evidence
# ══════════════════════════════════════════════════════════════════════════


def test_no_label_before_five_bars() -> None:
    """The engine returns None on the first four bars.

    A trend computed from three points is not a weak trend, it is an artefact of
    the sample size. Refusing to emit is the honest answer and it is the reason
    `current()` can legitimately be None for a symbol that has just started.
    """
    engine = _engine()

    states = asyncio.run(_feed(engine, [100.0, 100.5, 100.2, 100.4]))

    assert states == [None, None, None, None], states
    assert engine.current("AAPL") is None


def test_a_label_appears_exactly_when_evidence_does() -> None:
    engine = _engine()

    states = asyncio.run(_feed(engine, [100.0, 100.1, 100.2, 100.3, 100.4]))

    assert states[:4] == [None] * 4
    assert isinstance(states[4], RegimeState)
    assert states[4] is not None
    assert states[4].window_bars == 5


# ══════════════════════════════════════════════════════════════════════════
# The label names what it was derived from
# ══════════════════════════════════════════════════════════════════════════


def test_a_label_records_its_own_provenance() -> None:
    """The gate this file was written for, restated against the type that
    actually exists: the state names the symbol, the instant it was assessed at,
    how many bars it was derived from, and the measured inputs behind it."""
    engine = _engine()
    state = asyncio.run(_feed(engine, [100.0, 100.1, 100.2, 100.3, 100.4]))[4]

    assert state is not None
    assert state.symbol == "AAPL"
    assert state.assessed_at == T0 + timedelta(days=4)
    assert state.window_bars == 5
    # The measured inputs, not just the labels derived from them.
    assert isinstance(state.realized_vol_pct, float)
    assert isinstance(state.ema_slope_pct, float)
    assert state.trend in set(TrendLabel)
    assert state.vol_regime in set(VolRegime)


def test_current_returns_the_most_recent_label_only() -> None:
    engine = _engine()
    asyncio.run(_feed(engine, [100.0, 100.1, 100.2, 100.3, 100.4]))

    held = engine.current("AAPL")
    assert held is not None
    assert held.symbol == "AAPL"
    assert engine.current("MSFT") is None, "an unseen symbol has no state"


# ══════════════════════════════════════════════════════════════════════════
# CONSTITUTION.md 2.5, Honesty Law 1.3: simulated stays simulated
# ══════════════════════════════════════════════════════════════════════════


def test_is_simulated_is_carried_onto_every_label() -> None:
    """A replayed bar must be identifiable as replayed after labelling.

    This is the whole reason the flag is on the state rather than only on the
    input: the regime label is what downstream sizing reads, so a label that
    dropped the flag would launder a simulation into an observation.
    """
    simulated = _engine()
    live = _engine()

    from_simulation = asyncio.run(
        _feed(simulated, [100.0, 100.1, 100.2, 100.3, 100.4], simulated=True)
    )[4]
    from_market = asyncio.run(
        _feed(live, [100.0, 100.1, 100.2, 100.3, 100.4], simulated=False)
    )[4]

    assert from_simulation is not None and from_market is not None
    assert from_simulation.is_simulated is True
    assert from_market.is_simulated is False


# ══════════════════════════════════════════════════════════════════════════
# Trend and volatility labelling
# ══════════════════════════════════════════════════════════════════════════


def test_a_sustained_rise_labels_up_and_a_sustained_fall_labels_down() -> None:
    rising = _engine()
    states = asyncio.run(_feed(rising, [100.0 + i for i in range(12)]))
    labelled = [s for s in states if s is not None]
    assert labelled[-1].trend is TrendLabel.UP, labelled[-1]

    falling = _engine()
    states = asyncio.run(_feed(falling, [100.0 - i for i in range(12)]))
    labelled = [s for s in states if s is not None]
    assert labelled[-1].trend is TrendLabel.DOWN, labelled[-1]


def test_a_flat_series_does_not_invent_a_trend() -> None:
    """Constant prices give zero slope, which is FLAT -- not UP, and not an
    error. A labeller that cannot express 'nothing is happening' will report a
    trend for a still market."""
    engine = _engine()

    state = asyncio.run(_feed(engine, [100.0] * 12))[-1]

    assert state is not None
    assert state.trend is TrendLabel.FLAT
    assert state.ema_slope_pct == 0.0


def test_a_calm_series_is_low_volatility_and_a_jumpy_one_is_high() -> None:
    calm = _engine()
    calm_state = asyncio.run(_feed(calm, [100.0, 100.05, 100.1, 100.15, 100.2]))[-1]
    assert calm_state is not None
    assert calm_state.vol_regime is VolRegime.LOW, calm_state

    jumpy = _engine()
    jumpy_state = asyncio.run(_feed(jumpy, [100.0, 108.0, 92.0, 110.0, 95.0]))[-1]
    assert jumpy_state is not None
    assert jumpy_state.vol_regime is VolRegime.HIGH, jumpy_state


def test_labelling_is_deterministic() -> None:
    """Same bars, same label. A regime engine whose output depended on anything
    but its input would make every downstream backtest irreproducible."""
    closes = [100.0, 101.5, 99.5, 103.0, 97.0, 104.5]

    first = asyncio.run(_feed(_engine(), closes))[-1]
    second = asyncio.run(_feed(_engine(), closes))[-1]

    assert first is not None and second is not None
    assert first.trend is second.trend
    assert first.vol_regime is second.vol_regime
    assert first.realized_vol_pct == second.realized_vol_pct
    assert first.ema_slope_pct == second.ema_slope_pct


# ══════════════════════════════════════════════════════════════════════════
# Transition events
# ══════════════════════════════════════════════════════════════════════════


def test_regime_changed_is_published_on_a_change_and_not_on_the_first_label() -> None:
    """The first assessment is not a transition. Publishing it would make every
    symbol announce a change the moment it is first seen.

    `subscribe` is a coroutine, so it must be awaited before the bus is started.
    An earlier version of this test forgot, and passed vacuously: with nothing
    subscribed, `seen == []` was true for any input whatsoever.
    """
    bus = InMemoryEventBus()
    engine = _engine(bus)
    seen: list[object] = []

    async def run() -> None:
        await bus.subscribe(EventTopic.REGIME_CHANGED, lambda payload: seen.append(payload))
        await bus.start()
        # Flat first: establishes a state without a transition.
        await _feed(engine, [100.0] * 8)
        # The bus dispatches through a queue worker, so publishing is not
        # delivery. Draining is what turns "published" into "observed".
        await bus.wait_until_idle()
        assert seen == [], f"first label must not publish a change: {seen}"
        # Now a sustained rise, which must cross the trend threshold.
        await _feed(engine, [100.0 + i * 3.0 for i in range(8)])
        await bus.wait_until_idle()
        await bus.stop()

    asyncio.run(run())

    assert seen, (
        "a trend crossing from FLAT to UP must publish REGIME_CHANGED; an empty "
        "record here means the subscription is not wired, not that no "
        "transition occurred"
    )


def test_the_window_is_bounded() -> None:
    """The engine keeps a rolling window, so `window_bars` must not grow without
    limit on a long run -- an unbounded deque would make memory a function of
    uptime."""
    engine = _engine(window_bars=10)

    asyncio.run(_feed(engine, [100.0 + (i % 7) for i in range(60)]))
    state = engine.current("AAPL")

    assert state is not None
    assert state.window_bars == 10


# ══════════════════════════════════════════════════════════════════════════
# The sample standard deviation helper
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], 0.0),
        ([5.0], 0.0),
        ([2.0, 4.0], pytest.approx(1.41421356, rel=1e-6)),
        ([1.0, 1.0, 1.0], 0.0),
    ],
)
def test_statistics_stdev(values: list[float], expected: object) -> None:
    """Fewer than two samples cannot define a spread, so the answer is 0.0 rather
    than a division by zero or a NaN that would poison every comparison
    downstream."""
    assert statistics_stdev(values) == expected
