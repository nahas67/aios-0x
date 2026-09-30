"""Launch the AIOS-0X command center: replay a dataset, then serve UI+API.

Usage (detached): python scripts/serve_command_center.py [--port 8787]
Status written to data/command_center_status.json when ready.
"""

import argparse
import asyncio
import json
import pathlib
import sys
import threading
import time
from collections.abc import Coroutine
from typing import Any, TypeVar

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.server import CommandCenterServer, ServerIdentity, parse_token_map  # noqa: E402
from simulation.generate_golden_data import write_dataset  # noqa: E402
from simulation.replay_runner import ReplayRunner  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind address; use 0.0.0.0 only inside a container/reverse-proxy boundary",
    )
    parser.add_argument("--bars", type=int, default=240)
    parser.add_argument("--symbols", default="BTC/USD,ETH/USD")
    parser.add_argument("--balance", type=float, default=100000.0)
    parser.add_argument("--shadow", action="store_true", help="no cash mutation")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="skip LLM debate (deterministic research) for instant startup",
    )
    parser.add_argument("--db", default="data/command_center.db")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    data_dir = ROOT / "data" / "golden"
    dataset: dict[str, pathlib.Path] = {}
    for symbol in symbols:
        path = data_dir / f"{symbol.replace('/', '_')}_1d.csv"
        if not path.exists():
            write_dataset(data_dir, symbols=symbols, total_bars=max(args.bars, 60))
        if not path.exists():
            raise SystemExit(f"dataset missing for {symbol}")
        dataset[symbol] = path

    db_path = ROOT / args.db
    from core.config import get_settings

    settings = get_settings()
    if args.fast:
        # FIX 5: skip LLM debate entirely — instant startup, deterministic research.
        settings.research_mode = "deterministic"
    runner = ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=db_path,
        initial_balance=args.balance,
        shadow_mode=args.shadow,
        settings=settings,  # explicit .env opt-in for live LLM/news
        use_live_news=bool(settings.finnhub_api_key),
    )

    plane = runner.build_control_plane()
    from core.control_plane import AutonomyMode

    plane.autonomy = AutonomyMode(settings.autonomy_mode.upper())
    builder = runner.build_snapshot_builder()
    server = CommandCenterServer(
        builder,
        plane,
        port=args.port,
        host=args.host,
        auth_token=settings.api_auth_token,
        default_identity=ServerIdentity(
            operator_id=settings.server_operator_id,
            role=settings.server_default_role,
        ),
        identity_map=parse_token_map(settings.server_token_map),
    )
    server.start()

    def _replay() -> None:
        import traceback

        try:
            summary = asyncio.run(runner.run())
        except BaseException:
            traceback.print_exc()
            raise
        status = {
            "url": f"http://127.0.0.1:{server.port}",
            "ready": True,
            "research_mode": summary.research_mode_used,
            "model_calls": summary.model_calls,
            "model_cost_usd": summary.total_model_cost_usd,
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

    threading.Thread(target=_replay, name="replay", daemon=True).start()

    while True:
        time.sleep(3600)


_T = TypeVar("_T")


def asyncio_run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(coro)


if __name__ == "__main__":
    main()
