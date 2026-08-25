"""AIOS-0X operating system CLI.

    python -m aios boot                  # constitution gate + kernel boot inventory
    python -m aios replay --bars 120     # one honest replay, summary + exit code
    python -m aios serve --port 8787     # replay, then live command center (SSE)

One entrypoint for the whole system: the same kernel, runner, and authority
paths the tests exercise — booted the way an operating system boots.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------- boot


def cmd_boot(_args: argparse.Namespace) -> int:
    from core.constitution import enforce_at_boot
    from kernel.bootstrap import create_kernel

    constitution_hash = enforce_at_boot()
    kernel = create_kernel()

    print("AIOS-0X BOOT")
    print(f"  constitution : {constitution_hash[:16]}... PINNED")
    print(f"  actors       : {len(kernel.identity.list_all())}")
    print(f"  capabilities : {len(kernel.capabilities.list_capabilities())}")
    print("  lifecycles   : strategy/hypothesis/experiment")
    assert kernel.datasets is not None and kernel.experiments is not None
    print("  registries   : dataset/feature/model/experiment READY")
    print("  authority    : gateway FAIL-CLOSED (no implicit permission)")
    print("BOOT OK")
    return 0


# ------------------------------------------------------------------- replay


def _ensure_dataset(symbols: list[str], bars: int) -> dict[str, Path]:
    """Locate (or generate) golden CSVs. Existing files are NEVER rewritten —
    byte-stable datasets are what make reproducibility hashes meaningful."""

    from simulation.generate_golden_data import write_dataset

    data_dir = ROOT / "data" / "golden"
    data_dir.mkdir(parents=True, exist_ok=True)
    by_symbol: dict[str, Path] = {}
    regenerated = False
    for symbol in symbols:
        path = data_dir / f"{symbol.replace('/', '_')}_1d.csv"
        if not path.exists():
            write_dataset(data_dir, symbols=[symbol], total_bars=bars)
            regenerated = True
        by_symbol[symbol] = path
    if regenerated:
        print(f"dataset: generated {bars}-bar goldens in {data_dir}")
    else:
        sample = next(iter(by_symbol.values()))
        with open(sample, encoding="utf-8") as handle:
            rows = sum(1 for _ in handle) - 1
        print(
            f"dataset: using existing goldens ({rows} bars each in {data_dir}); "
            "--bars ignored for existing files"
        )
    return by_symbol


def _build_runner(args: argparse.Namespace) -> Any:
    from core.config import Settings
    from simulation.replay_runner import ReplayRunner

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    dataset = _ensure_dataset(symbols, args.bars)
    return ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=Path(args.db),
        initial_balance=args.balance,
        slippage_pct=args.slippage_pct,
        shadow_mode=getattr(args, "shadow", False),
        settings=Settings(model_provider="none"),
    )


def cmd_replay(args: argparse.Namespace) -> int:
    runner = _build_runner(args)
    summary = asyncio.run(runner.run())

    print("AIOS-0X REPLAY SUMMARY")
    fields = {
        "symbols": ",".join(summary.symbols),
        "bars": summary.total_bars,
        "trades_closed": summary.trades_closed,
        "wins/losses": f"{summary.wins}/{summary.losses}",
        "cumulative_pnl": round(summary.cumulative_pnl, 2),
        "final_equity": summary.final_equity,
        "max_drawdown_pct": summary.max_drawdown_pct,
        "directional_accuracy_pct": summary.directional_accuracy_pct,
        "alpha_vs_benchmark_pct": summary.alpha_pct,
        "postmortems": summary.postmortems_written,
        "events_audited": summary.events_logged,
        "chain_valid": summary.chain_valid,
        "determinism_hash": summary.determinism_hash[:16],
        "experiment_hash": summary.experiment_reproducibility_hash[:16],
    }
    for key, value in fields.items():
        print(f"  {key:26}: {value}")
    print("REPLAY OK" if summary.chain_valid else "REPLAY CHAIN BROKEN")
    return 0 if summary.chain_valid else 1


def cmd_summary_json(args: argparse.Namespace) -> int:
    """Machine-readable variant used by scripts/dashboards."""
    runner = _build_runner(args)
    summary = asyncio.run(runner.run())
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return 0 if summary.chain_valid else 1


# -------------------------------------------------------------------- serve


def _serve_forever(server: Any) -> None:
    """Blocking loop; overridable in tests."""
    while True:
        import time

        time.sleep(3600)


def cmd_serve(args: argparse.Namespace) -> int:
    from api.server import CommandCenterServer

    runner = _build_runner(args)
    summary = asyncio.run(runner.run())
    print(
        f"replay done: {summary.trades_closed} trades, "
        f"pnl {summary.cumulative_pnl:+.2f}, chain {'OK' if summary.chain_valid else 'BROKEN'}"
    )
    if not summary.chain_valid:
        print("refusing to serve: audit chain broken", file=sys.stderr)
        return 1

    server = CommandCenterServer(
        runner.build_snapshot_builder(), runner.build_control_plane(), port=args.port
    )
    server.start()
    print(f"command center: http://127.0.0.1:{server.port}  (Ctrl+C to stop)")
    try:
        _serve_forever(server)
    except KeyboardInterrupt:
        print("\nshutting down.")
        server.stop()
    return 0


# ------------------------------------------------------------------ parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aios", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("boot", help="constitution gate + kernel boot inventory")

    def _common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--bars", type=int, default=120)
        p.add_argument("--symbols", default="BTC/USD,ETH/USD")
        p.add_argument("--balance", type=float, default=100000.0)
        p.add_argument("--slippage-pct", type=float, default=0.05)
        p.add_argument("--db", default="data/aios.db")

    p_replay = sub.add_parser("replay", help="run one honest replay")
    _common(p_replay)

    p_json = sub.add_parser("summary-json", help="replay; machine-readable JSON summary")
    _common(p_json)

    p_serve = sub.add_parser("serve", help="replay, then live command center")
    _common(p_serve)
    p_serve.add_argument("--port", type=int, default=8787)
    p_serve.add_argument("--shadow", action="store_true", help="no cash mutation")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers: dict[str, Any] = {
        "boot": cmd_boot,
        "replay": cmd_replay,
        "summary-json": cmd_summary_json,
        "serve": cmd_serve,
    }
    return int(handlers[args.command](args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
