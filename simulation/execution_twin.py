"""Execution digital twin: latency decomposition with queue and impact (G160).

A claim that the fast tier earns its latency budget needs a place where
latency is the only variable: same order flow, same book, different
round-trip times. The twin replays a deterministic tick fixture through a
per-stage latency model (decide → transmit → venue → acknowledge), a queue
position that fills as trades consume the size ahead of it, partial fills
when a bar cannot absorb the child, and square-root market impact on
participation. Comparing 20/50/100/200 ms under identical conditions then
measures what latency costs, instead of asserting it.

Three honesties shape the implementation. First, latency acts on *staleness*:
a decision made at t executes against the book at t+L, so slower paths trade
worse prices on a drifting book — the measurable effect, not a penalty term.
Second, the queue is real state: size ahead decreases only when prints arrive,
and a child that the bar cannot fill stays partially open rather than
rounding itself complete. Third, the fixture is deterministic by closed form,
not by seed: a seeded generator reproduces only while the generator version
is pinned, while sin-based drift reproduces forever.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

__all__ = [
    "LatencyBudget",
    "Tick",
    "TwinConfig",
    "TwinFill",
    "TwinResult",
    "compare_latencies",
    "make_fixture_ticks",
    "run_twin",
]

#: Stage shares of a round trip. Fixed rather than fitted: the decomposition
#: exists to attribute cost per stage, and fitted shares would attribute by
#: assumption.
STAGE_SHARES: dict[str, float] = {
    "decide_ms": 0.30,
    "transmit_ms": 0.20,
    "venue_ms": 0.30,
    "ack_ms": 0.20,
}


@dataclass(frozen=True)
class Tick:
    """One print: timestamp, price, aggressor volume, and book depth."""

    t_ms: int
    price: float
    volume: float
    bid_size: float
    ask_size: float


@dataclass(frozen=True)
class LatencyBudget:
    """Per-stage decomposition of one round-trip target. The stages sum to
    the target by construction — a budget whose parts do not sum to its whole
    is a different budget wearing this one's name."""

    target_ms: float
    decide_ms: float
    transmit_ms: float
    venue_ms: float
    ack_ms: float

    @classmethod
    def split(cls, target_ms: float) -> LatencyBudget:
        if target_ms <= 0.0:
            raise ValueError(f"latency target must be positive; got {target_ms}")
        parts = {stage: target_ms * share for stage, share in STAGE_SHARES.items()}
        return cls(target_ms=target_ms, **parts)

    @property
    def action_delay_ms(self) -> float:
        """Decide + transmit + venue: how stale the book is when the child
        reaches it. The acknowledgement comes back after the fill, so it
        costs reporting latency, not price."""
        return self.decide_ms + self.transmit_ms + self.venue_ms


@dataclass(frozen=True)
class TwinConfig:
    """One replay: what to trade, how much queue to stand behind, how much
    size moves the price."""

    quantity: float
    side: str = "buy"
    impact_coefficient_bps: float = 10.0
    max_participation: float = 0.25

    def __post_init__(self) -> None:
        if self.quantity <= 0.0:
            raise ValueError("twin quantity must be positive")
        if self.side not in {"buy", "sell"}:
            raise ValueError(f"twin side must be buy or sell; got {self.side!r}")
        if not 0.0 < self.max_participation <= 1.0:
            raise ValueError("max_participation must lie in (0, 1]")


@dataclass(frozen=True)
class TwinFill:
    """One child's outcome: what filled, at what price, after what delay."""

    child_index: int
    requested: float
    filled: float
    avg_price: float
    arrival_t_ms: int
    fill_t_ms: int
    impact_bps: float

    @property
    def fill_rate(self) -> float:
        return self.filled / self.requested if self.requested > 0 else 0.0


@dataclass
class TwinResult:
    """Whole-run outcome at one latency target, with the stage attribution."""

    target_ms: float
    budget: LatencyBudget
    fills: list[TwinFill] = field(default_factory=list)
    unfilled: float = 0.0

    @property
    def fill_rate(self) -> float:
        requested = sum(f.requested for f in self.fills) + self.unfilled
        if requested <= 0.0:
            return 0.0
        return sum(f.filled for f in self.fills) / requested

    @property
    def volume_weighted_price(self) -> float:
        filled = sum(f.filled for f in self.fills)
        if filled <= 0.0:
            return 0.0
        return sum(f.filled * f.avg_price for f in self.fills) / filled

    @property
    def total_impact_bps(self) -> float:
        filled = sum(f.filled for f in self.fills)
        if filled <= 0.0:
            return 0.0
        return sum(f.filled * f.impact_bps for f in self.fills) / filled


def make_fixture_ticks(n: int = 400, drift_per_tick: float = 0.002) -> list[Tick]:
    """Deterministic book fixture: mid drifting up with sinusoidal wobble,
    constant spread, finite depth. Closed form, so it reproduces forever
    without pinning a generator version."""
    if n <= 0:
        raise ValueError("fixture needs at least one tick")
    ticks = []
    for i in range(n):
        mid = 100.0 + drift_per_tick * i + 0.05 * math.sin(i * 0.11)
        depth = 800.0 + 200.0 * math.sin(i * 0.05 + 1.0)
        ticks.append(
            Tick(
                t_ms=i * 100,
                price=round(mid, 4),
                volume=round(120.0 + 40.0 * math.sin(i * 0.07 + 2.0), 4),
                bid_size=round(depth, 4),
                ask_size=round(depth, 4),
            )
        )
    return ticks


def run_twin(
    ticks: list[Tick],
    config: TwinConfig,
    budget: LatencyBudget,
    *,
    children: int = 4,
) -> TwinResult:
    """Replay an even split of ``quantity`` over ``children`` slices.

    Each child is decided on the book at its slice time and executes against
    the book ``action_delay_ms`` later — the staleness latency buys. Queue
    position starts at the side's book size and fills as prints consume it;
    a slice that the remaining tape cannot absorb stays partially open and
    the remainder lands in ``unfilled`` rather than rounding complete. Impact
    follows the square-root law on participation, capped at
    ``max_participation``: size beyond the cap is refused by the bar, not
    silently printed.
    """
    if not ticks:
        raise ValueError("the twin needs ticks to replay")
    if children <= 0:
        raise ValueError("children must be positive")
    step = max(1, len(ticks) // children)
    result = TwinResult(target_ms=budget.target_ms, budget=budget)
    per_child = config.quantity / children
    sign = 1.0 if config.side == "buy" else -1.0

    for child in range(children):
        decide_at = child * step
        arrival_idx = decide_at
        arrival_t = ticks[decide_at].t_ms + budget.action_delay_ms
        while arrival_idx + 1 < len(ticks) and ticks[arrival_idx + 1].t_ms <= arrival_t:
            arrival_idx += 1
        book = ticks[arrival_idx]
        ahead = book.ask_size if config.side == "buy" else book.bid_size
        remaining = per_child
        filled = 0.0
        cost = 0.0
        impact_cost = 0.0
        cursor = arrival_idx
        while remaining > 1e-9 and cursor < len(ticks):
            tick = ticks[cursor]
            take = min(tick.volume * config.max_participation, remaining)
            consume = min(take, tick.volume)
            if ahead > 0.0:
                absorbed = min(ahead, consume)
                ahead -= absorbed
                consume -= absorbed
            fill_now = min(consume, remaining)
            participation = fill_now / tick.volume if tick.volume > 0 else 0.0
            impact = config.impact_coefficient_bps * math.sqrt(max(0.0, participation))
            price = tick.price * (1.0 + sign * impact / 10000.0)
            filled += fill_now
            cost += fill_now * price
            impact_cost += fill_now * impact
            remaining -= fill_now
            cursor += 1
        fill_t = ticks[min(cursor, len(ticks) - 1)].t_ms
        avg = cost / filled if filled > 0 else book.price
        result.fills.append(
            TwinFill(
                child_index=child,
                requested=per_child,
                filled=filled,
                avg_price=avg,
                arrival_t_ms=int(arrival_t),
                fill_t_ms=fill_t,
                impact_bps=impact_cost / filled if filled > 0 else 0.0,
            )
        )
        result.unfilled += remaining
    return result


def compare_latencies(
    ticks: list[Tick],
    config: TwinConfig,
    targets_ms: list[float],
    *,
    children: int = 4,
) -> dict[float, TwinResult]:
    """One fixture, several round-trips: latency is the only variable, so
    differences in fill rate and price are attributable to it. Targets must
    be distinct and positive; results key off the target."""
    if len(set(targets_ms)) != len(targets_ms):
        raise ValueError(f"latency targets must be distinct; got {targets_ms}")
    return {
        target: run_twin(ticks, config, LatencyBudget.split(target), children=children)
        for target in targets_ms
    }
