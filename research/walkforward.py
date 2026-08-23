"""Research tooling: walk-forward harness (Doc 06 defaults) + calibration.

WalkForward: rolling train/test windows over a golden dataset; the runner is
instantiated per window so every window is a fresh honest simulation.
Calibration: prediction-ledger reliability table + Brier score.
"""

import sqlite3
from collections.abc import Callable
from pathlib import Path

from schemas.contracts import (
    CalibrationBucket,
    CalibrationReport,
    WalkForwardReport,
    WalkWindowResult,
)

_MIN_CALIBRATION_SAMPLES = 20


def _sharpe(equity_curve: list[float]) -> float:
    if len(equity_curve) < 3:
        return 0.0
    returns = [(b - a) / a for a, b in zip(equity_curve, equity_curve[1:], strict=False)]
    n = len(returns)
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = float(variance**0.5)
    if std == 0:
        return 0.0
    sharpe: float = round(float(mean) / std * (n**0.5), 4)
    return sharpe


def _max_dd_pct(equity_curve: list[float]) -> float:
    peak = equity_curve[0] if equity_curve else 1.0
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak * 100.0)
    return round(worst, 4)


class WindowSlicer:
    """Cuts a CSV into contiguous train/test windows without look-ahead."""

    def __init__(self, total_bars: int, train_bars: int = 90, test_bars: int = 30) -> None:
        if train_bars <= 0 or test_bars <= 0:
            raise ValueError("window sizes must be positive")
        self.total_bars = total_bars
        self.train_bars = train_bars
        self.test_bars = test_bars

    def windows(self) -> list[tuple[int, int]]:
        """(start, end_exclusive) pairs covering successive test segments."""
        out: list[tuple[int, int]] = []
        start = 0
        while start + self.train_bars + min(1, self.test_bars) <= self.total_bars:
            end = min(start + self.train_bars + self.test_bars, self.total_bars)
            out.append((start, end))
            start += self.test_bars
        return out


async def run_walk_forward(
    csv_path: Path,
    store_dir: Path,
    make_runner: Callable[[Path, Path], object],
    train_bars: int = 90,
    test_bars: int = 30,
    in_sample_overfit_ratio: float = 2.0,
) -> WalkForwardReport:
    """Execute windows via ``make_runner(csv_window_path, store_path).run()``.

    ``make_runner`` must return an object with ``async run() -> RunSummary``
    and attribute ``equity_curve``; this keeps the harness decoupled from the
    concrete runner while demanding honest summaries.
    """
    lines = csv_path.read_text(encoding="utf-8").splitlines(keepends=True)
    header = lines[0]
    total_rows = len(lines) - 1

    slicer = WindowSlicer(total_rows, train_bars=train_bars, test_bars=test_bars)
    results: list[WalkWindowResult] = []

    for index, (start, end) in enumerate(slicer.windows()):
        seg_start = max(0, start - test_bars)  # small warmup tail reused as history
        window_csv = store_dir / f"window_{index}.csv"
        window_csv.write_text(header + "".join(lines[1 + seg_start : 1 + end]), encoding="utf-8")

        runner = make_runner(window_csv, store_dir / f"wf_{index}.db")
        summary = await runner.run()  # type: ignore[attr-defined]
        curve: list[float] = getattr(runner, "equity_curve", [])
        half = max(1, len(curve) // 2)
        train_proxy_sharpe = _sharpe(curve[:half])
        test_sharpe = _sharpe(curve[half:])

        results.append(
            WalkWindowResult(
                window_index=index,
                train_bars=end - seg_start - test_bars,
                test_bars=test_bars,
                test_trades=summary.trades_closed,
                test_pnl=summary.cumulative_pnl,
                test_sharpe=test_sharpe,
                test_max_dd_pct=_max_dd_pct(curve),
                overfit_flag=(
                    train_proxy_sharpe > in_sample_overfit_ratio * abs(test_sharpe)
                    and test_sharpe < 0
                ),
            )
        )

    aggregate = round(sum(r.test_pnl for r in results), 2)
    overfits = sum(1 for r in results if r.overfit_flag)
    return WalkForwardReport(
        windows=results,
        aggregate_test_pnl=aggregate,
        overfit_windows=overfits,
        passed=overfits == 0 and len(results) > 0,
    )


# ------------------------------------------------------------------ calibration


def calibration_report(conn: sqlite3.Connection) -> CalibrationReport:
    """Reliability buckets + Brier score from scored predictions.

    Probability proxy: verification confidence mapped to (0,1); direction_correct
    is the binary outcome. Honest minimum-sample gate before trusting buckets.
    """
    rows = conn.execute(
        "SELECT confidence_score, direction_correct FROM predictions "
        "WHERE status='SCORED' AND direction_correct IS NOT NULL"
    ).fetchall()
    total = len(rows)
    if total == 0:
        return CalibrationReport(
            total_scored=0,
            brier_score=0.0,
            directional_accuracy_pct=0.0,
            buckets=[],
            reliable=False,
        )

    brier_sum = 0.0
    correct = 0
    bucket_acc: dict[int, list[int]] = {}
    for row in rows:
        p = max(0.01, min(0.99, float(row["confidence_score"]) / 100.0))
        outcome = 1.0 if bool(row["direction_correct"]) else 0.0
        brier_sum += (p - outcome) ** 2
        correct += int(bool(row["direction_correct"]))
        decile = min(9, int(p * 10))
        bucket_acc.setdefault(decile, []).append(int(bool(row["direction_correct"])))

    buckets: list[CalibrationBucket] = []
    for decile in sorted(bucket_acc):
        outcomes = bucket_acc[decile]
        buckets.append(
            CalibrationBucket(
                confidence_low=decile * 10.0,
                confidence_high=(decile + 1) * 10.0,
                predictions=len(outcomes),
                empirical_accuracy_pct=round(sum(outcomes) / len(outcomes) * 100.0, 2),
                avg_confidence_pct=(decile + 0.5) * 10.0,
            )
        )

    return CalibrationReport(
        total_scored=total,
        brier_score=round(brier_sum / total, 6),
        directional_accuracy_pct=round(correct / total * 100.0, 2),
        buckets=buckets,
        reliable=total >= _MIN_CALIBRATION_SAMPLES,
    )
