"""CLI: run an honest historical replay over golden datasets.

Example:
    python scripts/run_replay.py --data-dir data/golden --db data/replay.db
"""

import argparse
import asyncio
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from simulation.replay_runner import ReplayRunner  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/golden", help="Directory of *_1d.csv files")
    parser.add_argument("--db", default="data/replay.db", help="SQLite store path")
    parser.add_argument("--balance", type=float, default=100000.0)
    parser.add_argument("--slippage-pct", type=float, default=0.05)
    args = parser.parse_args()

    data_dir = pathlib.Path(args.data_dir)
    csvs = sorted(data_dir.glob("*_1d.csv"))
    if not csvs:
        print(f"No *_1d.csv datasets in {data_dir}; run generate_golden_data first.")
        sys.exit(1)

    dataset = {path.name.replace("_1d.csv", "").replace("_", "/"): path for path in csvs}
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    runner = ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=args.db,
        initial_balance=args.balance,
        slippage_pct=args.slippage_pct,
    )
    summary = asyncio.run(runner.run())
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
