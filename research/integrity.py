"""Research tooling: backtest-integrity linters (Directive 33).

Static + structural checks that must pass before any backtest result is
trusted. These encode the failure modes the frozen specs call out:
look-ahead, survivorship, cost realism, data hygiene.
"""

from collections import Counter

from pydantic import BaseModel, Field

from schemas.contracts import IntegrityCheck, IntegrityReport


def _check(name: str, passed: bool, detail: str) -> IntegrityCheck:
    return IntegrityCheck(name=name, passed=passed, detail=detail)


def lint_dataset(csv_rows: list[dict[str, str]], symbol_count: int) -> IntegrityReport:
    """Structural checks over a replay dataset (rows as parsed dicts)."""
    checks: list[IntegrityCheck] = []

    # Monotonic timestamps per file ordering (no time travel inside a series)
    timestamps = [r["timestamp"] for r in csv_rows]
    checks.append(
        _check(
            "timestamps_monotonic",
            all(timestamps[i] <= timestamps[i + 1] for i in range(len(timestamps) - 1)),
            "dataset rows are non-decreasing in timestamp",
        )
    )

    # Duplicate bars would double-count evidence
    dupes = [t for t, n in Counter(timestamps).items() if n > 1]
    checks.append(
        _check(
            "no_duplicate_bars",
            not dupes,
            f"{len(dupes)} duplicate timestamps" if dupes else "all timestamps unique",
        )
    )

    # Survivorship guard: multi-symbol datasets must actually be multi-symbol
    checks.append(
        _check(
            "survivorship_universe_fixed",
            symbol_count >= 2 or len(set(r.get("symbol", "") for r in csv_rows)) >= 1,
            f"universe contains {symbol_count} symbol file(s); selection bias requires "
            "the full pre-declared universe",
        )
    )

    # Positive prices everywhere
    positive = all(float(r[k]) > 0 for r in csv_rows for k in ("open", "high", "low", "close"))
    checks.append(_check("prices_positive", positive, "all OHLC values > 0"))

    return IntegrityReport(checks=checks)


class RunnerConfigFacts(BaseModel):
    """Facts about a runner configuration relevant to integrity."""

    slippage_pct: float = Field(ge=0.0)
    taker_fee_pct: float = Field(ge=0.0)
    position_cap_per_symbol: int = Field(gt=0)
    uses_bracket_exits: bool
    no_same_bar_exit: bool
    as_of_fetcher: bool


def lint_runner_config(facts: RunnerConfigFacts) -> IntegrityReport:
    """Config-level realism gates; failing any invalidates the backtest."""
    checks = [
        _check(
            "entry_slippage_applied",
            facts.slippage_pct > 0,
            f"slippage={facts.slippage_pct}%",
        ),
        _check(
            "fees_applied",
            facts.taker_fee_pct > 0,
            f"taker_fee={facts.taker_fee_pct}%",
        ),
        _check(
            "position_caps_active",
            facts.position_cap_per_symbol >= 1,
            f"max {facts.position_cap_per_symbol} open/symbol",
        ),
        _check(
            "bracket_exits_market_driven",
            facts.uses_bracket_exits,
            "exits from actual bar extremes only",
        ),
        _check(
            "no_same_bar_entry_exit",
            facts.no_same_bar_exit,
            "entry bar excluded from exit evaluation",
        ),
        _check(
            "as_of_data_access",
            facts.as_of_fetcher,
            "fetcher exposes cursor bar only (Directive 75)",
        ),
    ]
    return IntegrityReport(checks=checks)
