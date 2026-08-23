"""Execute the walk-forward harness over golden data; persist an honest report.

Usage: python scripts/run_walk_forward.py [--bars 300] [--train 90] [--test 30]
"""

import argparse
import asyncio
import json
import logging
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

logging.disable(logging.WARNING)

from research.integrity import RunnerConfigFacts, lint_runner_config  # noqa: E402
from research.walkforward import run_walk_forward  # noqa: E402
from simulation.generate_golden_data import write_dataset  # noqa: E402
from simulation.replay_runner import ReplayRunner  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=int, default=300)
    parser.add_argument("--train", type=int, default=90)
    parser.add_argument("--test", type=int, default=30)
    args = parser.parse_args()

    d = pathlib.Path(tempfile.mkdtemp())
    write_dataset(d / "golden", symbols=["BTC/USD"], total_bars=args.bars)
    csv_path = d / "golden" / "BTC_USD_1d.csv"

    integrity = lint_runner_config(
        RunnerConfigFacts(
            slippage_pct=0.05,
            taker_fee_pct=0.1,
            position_cap_per_symbol=1,
            uses_bracket_exits=True,
            no_same_bar_exit=True,
            as_of_fetcher=True,
        )
    )
    assert integrity.passed, "runner config failed integrity gates - refusing to trust results"

    def make_runner(window_csv: pathlib.Path, store_path: pathlib.Path) -> ReplayRunner:
        return ReplayRunner(
            csv_path_by_symbol={"BTC/USD": window_csv},
            store_path=store_path,
            initial_balance=100000.0,
        )

    report = asyncio.run(
        run_walk_forward(csv_path, d, make_runner, train_bars=args.train, test_bars=args.test)
    )

    out_dir = pathlib.Path("research/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"walk_forward_{args.bars}b_{args.train}t{args.test}s.json"
    payload = {
        "integrity": integrity.model_dump(mode="json"),
        "walk_forward": report.model_dump(mode="json"),
        "note": (
            "Synthetic golden data (seeded SIM). Demonstrates harness honesty "
            "mechanics; NOT evidence of real-market edge."
        ),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"windows={len(report.windows)} aggregate_pnl={report.aggregate_test_pnl} "
        f"overfit_windows={report.overfit_windows} passed={report.passed}"
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
