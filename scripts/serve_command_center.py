"""Launch the AIOS-0X command center: replay a dataset, then serve UI+API.

Usage (detached): python scripts/serve_command_center.py [--port 8787]
Status written to data/command_center_status.json when ready.
"""

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.server import CommandCenterServer  # noqa: E402
from simulation.generate_golden_data import write_dataset  # noqa: E402
from simulation.replay_runner import ReplayRunner  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--bars", type=int, default=240)
    parser.add_argument("--symbols", default="BTC/USD,ETH/USD")
    parser.add_argument("--balance", type=float, default=100000.0)
    parser.add_argument("--shadow", action="store_true", help="no cash mutation")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    data_dir = ROOT / "data" / "golden"
    dataset = {}
    for symbol in symbols:
        path = data_dir / f"{symbol.replace('/', '_')}_1d.csv"
        if not path.exists():
            write_dataset(data_dir, symbols=symbols, total_bars=max(args.bars, 60))
        if not path.exists():
            raise SystemExit(f"dataset missing for {symbol}")
        dataset[symbol] = path

    db_path = ROOT / "data" / "command_center.db"
    from core.config import get_settings

    runner = ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=db_path,
        initial_balance=args.balance,
        shadow_mode=args.shadow,
        settings=get_settings(),  # explicit .env opt-in for live LLM/news
        use_live_news=bool(get_settings().finnhub_api_key),
    )
    summary = asyncio_run(runner.run())

    plane = runner.build_control_plane()
    builder = runner.build_snapshot_builder()
    server = CommandCenterServer(builder, plane, port=args.port)
    server.start()

    status = {
        "url": f"http://127.0.0.1:{server.port}",
        "ready": True,
        "research_mode": summary.research_mode_used,
        "trades_closed": summary.trades_closed,
        "cumulative_pnl": summary.cumulative_pnl,
        "directional_accuracy_pct": summary.directional_accuracy_pct,
        "emergency_state": "NORMAL",
        "chain_valid": summary.chain_valid,
        "symbols": symbols,
        "shadow_mode": args.shadow,
    }
    (ROOT / "data" / "command_center_status.json").write_text(
        json.dumps(status, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, indent=2), flush=True)

    while True:
        time.sleep(3600)


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


if __name__ == "__main__":
    main()
