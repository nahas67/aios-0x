"""Measured backtest evidence, so certification cannot be self-asserted (G080).

The certification firewall originally took booleans from its caller:
``capacity_modelled=True``. That is not a check, it is a promise, and a promise
is exactly what a failing process makes. This module exists so the three
operational checks are *derived from numbers* instead.

Three measurements, each a real model rather than a flag:

**Net of costs.** A gross Sharpe is not a result. Every backtest here returns
both gross and net series, and the firewall can tell the difference between
"costs were applied" and "costs were declared". A strategy whose net and gross
Sharpe are identical has had no cost model attached, whatever the caller said.

**Capacity, via the square-root law.** Market impact grows with the square
root of participation, not linearly. A strategy's edge therefore erodes as size
grows, and the eroding point is the honest capacity ceiling. Measured by
sweeping notional and finding the largest size whose net Sharpe still clears
the bar. Asserting a capacity number instead of measuring it produces a claim
that grows exactly when it should be shrinking.

**Stress and execution.** The same series re-run under a declared shock, and
with a declared fill model. A strategy that only works on a clean tape is not
a strategy, and the only way to know is to break the tape.

Everything is deterministic and dependency-free, because a certification number
must be reproducible by whoever reads it months later.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from core.quant_statistics import sharpe_ratio

__all__ = [
    "BacktestResult",
    "CostModel",
    "ExecutionModel",
    "RegimeSlice",
    "StressScenario",
    "capacity_ceiling",
    "regime_sharpes",
    "run_backtest",
    "worst_case_sharpe",
]


@dataclass(frozen=True)
class CostModel:
    """Explicit trading frictions, in basis points of traded notional.

    ``impact_coefficient`` drives the square-root law: impact scales with
    ``coefficient * sqrt(participation)``. A zero coefficient is legal but
    means no market impact at all, which is the assumption that makes most
    published backtests unreachable in practice.
    """

    commission_bps: float = 1.0
    half_spread_bps: float = 1.0
    impact_coefficient_bps: float = 10.0

    def round_trip_bps(self) -> float:
        """Fixed cost of entering and exiting, in bps."""
        return 2.0 * (self.commission_bps + self.half_spread_bps)

    def impact_bps(self, participation: float) -> float:
        """Square-root-law market impact for a given participation rate.

        Zero participation costs nothing, and impact grows as the square root
        rather than linearly, which is why doubling size costs ~41% more in
        impact rather than 100%.
        """
        if participation <= 0.0:
            return 0.0
        return self.impact_coefficient_bps * math.sqrt(participation)

    def is_degenerate(self) -> bool:
        """True when this model cannot produce a measurable cost.

        Detecting this is the point: it is how a net figure becomes
        distinguishable from a gross one.
        """
        return self.round_trip_bps() <= 0.0 and self.impact_coefficient_bps <= 0.0


@dataclass(frozen=True)
class ExecutionModel:
    """How fills actually happen, beyond the cost model's fixed frictions."""

    latency_bars: int = 0
    partial_fill_ratio: float = 1.0
    rejected_rate: float = 0.0

    def is_frictionless(self) -> bool:
        """True when execution is assumed perfect.

        Zero latency, full fills, and no rejections together describe a venue
        that does not exist, so a strategy certified under them is certified
        against a fiction.
        """
        return (
            self.latency_bars == 0
            and self.partial_fill_ratio >= 1.0
            and self.rejected_rate <= 0.0
        )


@dataclass(frozen=True)
class StressScenario:
    """A named disruption applied to a price series before re-running."""

    name: str
    #: Multiplicative price shock applied at the scenario's bar, e.g. -0.30.
    shock: float
    #: Multiplicative volatility scaling applied to subsequent returns.
    volatility_multiplier: float = 1.0
    #: Index at which the shock lands, as a fraction of the series length.
    at_fraction: float = 0.5


@dataclass(frozen=True)
class BacktestResult:
    """The measured outcome of one run, gross and net.

    Both series are retained. The firewall's cost check is literally
    ``net == gross``, so a result that claims to be net-of-cost while being
    identical to gross is caught here rather than believed.
    """

    gross_returns: list[float]
    net_returns: list[float]
    gross_sharpe: float
    net_sharpe: float
    participation: float
    cost_bps: float
    n_trades: int
    periods_per_year: int = 252

    @property
    def cost_drag(self) -> float:
        """Sharpe lost to costs. Zero means the cost model did nothing."""
        return self.gross_sharpe - self.net_sharpe

    @property
    def costs_applied(self) -> bool:
        """Whether costs measurably changed the result.

        Measured, not declared. A backtest with no cost model produces an
        identical gross and net series, and that is detectable without trusting
        anything the caller says.
        """
        if len(self.gross_returns) != len(self.net_returns):
            return True
        return any(
            abs(g - n) > 1e-12 for g, n in zip(self.gross_returns, self.net_returns, strict=True)
        )

    @property
    def is_flat(self) -> bool:
        return self.net_sharpe == 0.0


def _returns_from_prices(prices: Sequence[float]) -> list[float]:
    if len(prices) < 2:
        return []
    return [prices[i + 1] / prices[i] - 1.0 for i in range(len(prices) - 1)]


def run_backtest(
    signals: Sequence[int],
    prices: Sequence[float],
    *,
    volumes: Sequence[float] | None = None,
    notional: float = 100_000.0,
    costs: CostModel | None = None,
    execution: ExecutionModel | None = None,
    periods_per_year: int = 252,
) -> BacktestResult:
    """Run a signal series over a price series, gross and net.

    Args:
        signals: Target position per bar in ``{-1, 0, 1}``.
        prices: Close per bar. Must be same length as ``signals``.
        volumes: Traded volume per bar, for the participation rate. Omitted
            volumes disable impact, which is itself a measured deficiency:
            :attr:`BacktestResult.costs_applied` will be false unless the fixed
            round trip is non-zero.
        notional: USD traded per position change.
        costs: Friction model; defaults to a realistic one.
        execution: Fill model; defaults to frictionless, which the firewall
            detects rather than trusts.
        periods_per_year: Annualisation factor for the Sharpe.

    Returns:
        A :class:`BacktestResult` carrying both series and the participation
        rate actually used, so a capacity claim can be traced to a size.
    """
    cost_model = costs or CostModel()
    fill = execution or ExecutionModel()
    n = min(len(signals), len(prices))
    if n < 2:
        return BacktestResult(
            gross_returns=[],
            net_returns=[],
            gross_sharpe=0.0,
            net_sharpe=0.0,
            participation=0.0,
            cost_bps=0.0,
            n_trades=0,
            periods_per_year=periods_per_year,
        )

    bar_returns = _returns_from_prices(prices[:n])
    gross: list[float] = []
    net: list[float] = []
    position = 0
    trades = 0
    participation = 0.0

    for i, bar_return in enumerate(bar_returns):
        target = int(signals[i + 1])
        turnover = abs(target - position)
        bar_cost = 0.0
        if turnover:
            trades += 1
            traded_notional = notional * turnover
            volume = volumes[i] if volumes is not None and i < len(volumes) else 0.0
            bar_volume_notional = volume * prices[i] if volume > 0 and prices[i] > 0 else 0.0
            if bar_volume_notional > 0:
                rate = traded_notional / bar_volume_notional
                participation = max(participation, rate)
                bar_cost += cost_model.impact_bps(rate)
            bar_cost += cost_model.round_trip_bps() * turnover / 2.0

        if fill.partial_fill_ratio < 1.0:
            bar_cost += cost_model.half_spread_bps * (1.0 - fill.partial_fill_ratio)
        if fill.rejected_rate > 0.0:
            bar_cost += cost_model.half_spread_bps * fill.rejected_rate

        earned = position * bar_return
        gross.append(earned)
        net.append(earned - bar_cost / 10_000.0)
        position = target

    return BacktestResult(
        gross_returns=gross,
        net_returns=net,
        gross_sharpe=sharpe_ratio(gross, periods_per_year=periods_per_year),
        net_sharpe=sharpe_ratio(net, periods_per_year=periods_per_year),
        participation=participation,
        cost_bps=cost_model.round_trip_bps(),
        n_trades=trades,
        periods_per_year=periods_per_year,
    )


def capacity_ceiling(
    signals: Sequence[int],
    prices: Sequence[float],
    *,
    volumes: Sequence[float] | None,
    target_notionals: Sequence[float],
    min_net_sharpe: float = 1.0,
    costs: CostModel | None = None,
    execution: ExecutionModel | None = None,
    periods_per_year: int = 252,
) -> float:
    """Largest notional whose net Sharpe still clears ``min_net_sharpe``.

    Sweeps the supplied sizes and returns the biggest one that passes, or 0.0
    when none does. A *measured* ceiling rather than an asserted one: the
    caller cannot state a capacity, only the sizes they intend to certify, and
    the model decides which of those survive its own impact.
    """
    passing: list[float] = []
    for notional in sorted(target_notionals):
        if notional <= 0:
            continue
        result = run_backtest(
            signals,
            prices,
            volumes=volumes,
            notional=notional,
            costs=costs,
            execution=execution,
            periods_per_year=periods_per_year,
        )
        if result.net_sharpe >= min_net_sharpe:
            passing.append(float(notional))
    return max(passing) if passing else 0.0


def apply_stress(prices: Sequence[float], scenario: StressScenario) -> list[float]:
    """Apply a named disruption to a price series.

    Deterministic given the input, so a stress result is reproducible by
    whoever reads the certification report.
    """
    if not prices:
        return []
    index = min(len(prices) - 1, max(0, int(scenario.at_fraction * len(prices))))
    stressed: list[float] = []
    for i, price in enumerate(prices):
        value = price
        if i >= index:
            value = price * (1.0 + scenario.shock)
            if i > index and scenario.volatility_multiplier != 1.0 and prices[i - 1] > 0:
                # Amplify the return around the shock, then re-anchor to level.
                amplified = (value / prices[i - 1] - 1.0) * scenario.volatility_multiplier
                value = prices[i - 1] * (1.0 + amplified)
        stressed.append(max(value, 1e-9))
    return stressed


#: The default disruption set. A crash, a volatility blowout, and a grind are
#: three different ways a strategy dies, and a certification that runs only one
#: of them has tested one thing.
DEFAULT_STRESS_SCENARIOS: tuple[StressScenario, ...] = (
    StressScenario("crash", shock=-0.30, volatility_multiplier=1.8, at_fraction=0.5),
    StressScenario("vol_blowout", shock=-0.05, volatility_multiplier=3.0, at_fraction=0.4),
    StressScenario("grind", shock=-0.10, volatility_multiplier=0.6, at_fraction=0.6),
)


def worst_case_sharpe(
    signals: Sequence[int],
    prices: Sequence[float],
    *,
    volumes: Sequence[float] | None,
    notional: float,
    scenarios: Sequence[StressScenario] | None = None,
    costs: CostModel | None = None,
    execution: ExecutionModel | None = None,
    periods_per_year: int = 252,
) -> tuple[float, str]:
    """Worst net Sharpe across the stress set, with the scenario's name.

    Returns ``(sharpe, name)``. A strategy that only works on a clean tape
    shows it here, on the scenario that hurt it, rather than in a footnote.
    """
    used = list(scenarios if scenarios is not None else DEFAULT_STRESS_SCENARIOS)
    if not used:
        return 0.0, "none"
    worst = math.inf
    culprit = used[0].name
    for scenario in used:
        stressed = apply_stress(prices, scenario)
        result = run_backtest(
            signals,
            stressed,
            volumes=volumes,
            notional=notional,
            costs=costs,
            execution=execution,
            periods_per_year=periods_per_year,
        )
        if result.net_sharpe < worst:
            worst = result.net_sharpe
            culprit = scenario.name
    return worst, culprit


@dataclass(frozen=True)
class RegimeSlice:
    """How the strategy performed inside one named regime.

    A measurement, not a label. The labels arrive as data — one per return,
    typically a point-in-time observable such as a volatility tercile — and
    this function reports what the net series did under each one. A regime the
    strategy never traded in has no Sharpe here, which is itself the finding:
    a playbook cannot be published for a state with no measured performance.
    """

    regime: str
    net_sharpe: float
    n_observations: int


def regime_sharpes(
    net_returns: Sequence[float],
    labels: Sequence[str],
    *,
    periods_per_year: int = 252,
) -> dict[str, RegimeSlice]:
    """Net Sharpe per regime label, with the observation count behind each.

    Raises on a length mismatch rather than truncating or padding. A label
    series that does not align with the return series is a join error, and a
    join error resolved by silently dropping the tail is how a regime
    decomposition ends up describing a different sample than the backtest.

    Each slice uses :func:`core.quant_statistics.sharpe_ratio`, so a regime
    with fewer than two observations reports 0.0 rather than raising — a thin
    slice is a real observation with no measurable edge, and the certification
    floor on observation counts is what refuses it, not an exception here.
    """
    returns = list(net_returns)
    names = list(labels)
    if len(returns) != len(names):
        raise ValueError(
            f"{len(returns)} returns but {len(names)} regime labels. A decomposition "
            "over a misaligned join describes a different sample than the backtest."
        )
    buckets: dict[str, list[float]] = {}
    for ret, name in zip(returns, names, strict=True):
        buckets.setdefault(name, []).append(ret)
    return {
        name: RegimeSlice(
            regime=name,
            net_sharpe=sharpe_ratio(series, periods_per_year=periods_per_year),
            n_observations=len(series),
        )
        for name, series in buckets.items()
    }
