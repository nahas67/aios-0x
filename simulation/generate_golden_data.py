"""Deterministic synthetic OHLCV generator producing the Phase 1 golden datasets.

Constitution Law 1.3 compliance: every file produced here is SIMULATED and is
consumed only through adapters that tag payloads is_simulated=True. Real,
licensed market data replaces these files in Phase 3 without interface changes.

Seeded regime-switching geometric walk: trend-up / chop / trend-down / shock
regimes with fixed PRNG seed produce byte-stable datasets across machines.
"""

import argparse
import csv
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

_UNIVERSE: dict[str, float] = {
    "BTC/USD": 42000.0,
    "ETH/USD": 2200.0,
    "SOL/USD": 95.0,
    "AAPL": 185.0,
    "MSFT": 370.0,
    "SPY": 475.0,
    "QQQ": 405.0,
}

# Regime sequence: (bars, daily drift, daily sigma)
_REGIMES: list[tuple[int, float, float]] = [
    (60, 0.0012, 0.010),  # steady uptrend
    (30, 0.0000, 0.006),  # chop
    (45, -0.0018, 0.016),  # correction
    (90, 0.0006, 0.008),  # recovery grind
    (25, 0.0000, 0.035),  # volatility shock
    (60, -0.0008, 0.012),  # risk-off drift
    (75, 0.0015, 0.011),  # renewed bull
]

_START = datetime(2024, 1, 1, tzinfo=UTC)
_END_EXCLUSIVE = datetime(2025, 12, 31, tzinfo=UTC)


def generate_series(seed_offset: int, s0: float, total_bars: int) -> list[dict[str, object]]:
    """Generate one deterministic OHLCV series."""
    rng = random.Random(42 + seed_offset)
    rows: list[dict[str, object]] = []
    price = s0
    ts = _START
    regime_idx = 0
    bars_left_in_regime = _REGIMES[0][0]
    base_volume = 50_000.0

    while len(rows) < total_bars and ts < _END_EXCLUSIVE:
        if bars_left_in_regime == 0:
            regime_idx = (regime_idx + 1) % len(_REGIMES)
            bars_left_in_regime = _REGIMES[regime_idx][0]
        _, mu, sigma = _REGIMES[regime_idx]
        bars_left_in_regime -= 1

        ret = rng.gauss(mu, sigma)
        open_price = price
        close_price = max(open_price * math.exp(ret), 0.01)
        wick_up = abs(rng.gauss(0, sigma * 0.6))
        wick_down = abs(rng.gauss(0, sigma * 0.6))
        high_price = max(open_price, close_price) * (1 + wick_up)
        low_price = min(open_price, close_price) * (1 - wick_down)
        volume = base_volume * math.exp(rng.gauss(0, 0.35))

        rows.append(
            {
                "timestamp": ts.isoformat(),
                "open": round(open_price, 6),
                "high": round(high_price, 6),
                "low": round(low_price, 6),
                "close": round(close_price, 6),
                "volume": round(volume, 2),
            }
        )
        price = close_price
        ts += timedelta(days=1)
    return rows


def write_dataset(
    out_dir: Path, symbols: list[str] | None = None, total_bars: int = 730
) -> list[Path]:
    """Write one CSV per symbol; returns written paths (deterministic content)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen = symbols if symbols else list(_UNIVERSE)
    paths: list[Path] = []
    for offset, symbol in enumerate(sorted(chosen)):
        s0 = _UNIVERSE[symbol]
        rows = generate_series(offset, s0, total_bars)
        path = out_dir / f"{symbol.replace('/', '_')}_1d.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"]
            )
            writer.writeheader()
            writer.writerows(rows)
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/golden", help="Output directory")
    parser.add_argument("--bars", type=int, default=730, help="Bars per symbol (~2y daily)")
    args = parser.parse_args()
    written = write_dataset(Path(args.out), total_bars=args.bars)
    for path in written:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
