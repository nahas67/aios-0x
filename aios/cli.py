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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from core.financial_kernel import BaseFinancialStore

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


# ------------------------------------------------------------------- events


def cmd_events(args: argparse.Namespace) -> int:
    """Durable recovery: read events after a cursor (§26 crash-recovery seam)."""
    from core.event_recovery import EventReplay, checkpoint

    store = _open_store(args.db)
    mark = checkpoint(store)
    print(f"log checkpoint: seq {mark}")
    replay = EventReplay(store, after_seq=args.after)
    batch = replay.drain(kind_prefix=args.kind or None)
    shown = 0
    for event in batch:
        if shown >= args.limit:
            print(f"... {len(batch) - args.limit} more (raise --limit)")
            break
        payload_preview = json.dumps(event["payload"])[:110]
        print(f"{event['seq']:>6}  {event['ts'][:19]}  {event['kind']:<42} {payload_preview}")
        shown += 1
    print(f"replayed {min(len(batch), args.limit)} of {len(batch)} events after seq {args.after}")
    return 0


def _open_store(db: str) -> Any:
    from core.persistence import SqliteMemoryStore

    return SqliteMemoryStore(Path(db))


# --------------------------------------------------------------------- tail


def cmd_tail(args: argparse.Namespace) -> int:
    """Independent consumer process: follow the durable log from a cursor.

    This is the multi-process seam (§26 + §2): the trading OS writes the
    hash-chained log; ANY number of processes consume it independently —
    analytics, alerting, research services — each with its own cursor.
    """
    import time

    from core.event_recovery import EventReplay, checkpoint

    store = _open_store(args.db)

    after_seq = args.after
    if args.state_file:
        state_path = Path(args.state_file)
        if state_path.exists():
            try:
                after_seq = int(json.loads(state_path.read_text())["after_seq"])
            except (ValueError, KeyError):
                print(f"bad state file {state_path}; falling back", file=sys.stderr)
                after_seq = checkpoint(store) if args.follow else args.after
        else:
            # fresh consumer: --follow starts from NOW; one-shot honours --after
            after_seq = checkpoint(store) if args.follow else args.after
    elif args.follow:
        after_seq = checkpoint(store)

    print(f"tail {args.db} from seq {after_seq} (poll={args.poll_interval}s)", flush=True)
    replay = EventReplay(store, after_seq=after_seq)
    idle = False
    try:
        while True:
            batch = replay.next(limit=args.batch)
            for event in batch:
                line = (
                    json.dumps(
                        {
                            "seq": event["seq"],
                            "ts": event["ts"],
                            "kind": event["kind"],
                            "ref_id": event["ref_id"],
                            "payload": event["payload"],
                        }
                    )
                    if args.json
                    else f"{event['seq']:>6}  {event['ts'][:19]}  {event['kind']:<42} {event['ref_id'] or ''}"
                )
                print(line, flush=True)
            if args.state_file and batch:
                Path(args.state_file).write_text(json.dumps({"after_seq": replay.after_seq}))
            idle = not batch
            if not args.follow:
                if idle:
                    break
                continue
            time.sleep(args.poll_interval if idle else 0.0)
    except KeyboardInterrupt:
        pass
    return 0


# --------------------------------------------------------------- database


def _open_financial_store(
    args: argparse.Namespace, *, auto_migrate: bool = False
) -> "BaseFinancialStore":
    """Open the configured financial store (PostgreSQL DSN or local SQLite)."""
    from core.financial_kernel import SqliteFinancialStore
    from core.pg_financial_store import PostgresFinancialStore

    dsn = args.dsn or ""
    if dsn.startswith(("postgres://", "postgresql://")):
        return PostgresFinancialStore(dsn, auto_migrate=auto_migrate)
    return SqliteFinancialStore(args.sqlite)


def cmd_db(args: argparse.Namespace) -> int:
    """`aios db status|migrate`: versioned financial schema management.

    Production never creates tables implicitly, so migration is an explicit,
    auditable operator action; rollback is a restore-from-backup step (see
    docs/DEVELOPMENT.md), because forward-only DDL cannot un-drop a column.
    """
    from core.migrations import (
        apply_postgres_migrations,
        apply_sqlite_migrations,
        latest_version,
        schema_status,
    )

    if args.db_command == "migrate":
        if args.dsn.startswith(("postgres://", "postgresql://")):
            import psycopg

            with psycopg.connect(args.dsn) as conn:
                applied = apply_postgres_migrations(conn)
                conn.commit()
                status = schema_status(conn, dialect="postgres")
        else:
            import sqlite3

            # Separate names per dialect: the two driver connections are
            # unrelated types, and reusing one name would make this branch a
            # reassignment between them rather than a fresh local binding.
            sqlite_conn = sqlite3.connect(args.sqlite)
            sqlite_conn.row_factory = sqlite3.Row
            applied = apply_sqlite_migrations(sqlite_conn)
            status = schema_status(sqlite_conn, dialect="sqlite")
            sqlite_conn.close()
        print(f"applied migrations: {applied or 'none (already current)'}")
        print(f"schema now at v{status['current']} (required v{latest_version()})")
        return 0 if status["up_to_date"] else 1

    # status
    if args.dsn.startswith(("postgres://", "postgresql://")):
        import psycopg

        with psycopg.connect(args.dsn) as conn:
            status = schema_status(conn, dialect="postgres")
    else:
        import sqlite3

        sqlite_conn = sqlite3.connect(args.sqlite)
        status = schema_status(sqlite_conn, dialect="sqlite")
        sqlite_conn.close()
    print(json.dumps(status, indent=2, default=str))
    return 0 if status["up_to_date"] else 1


def cmd_finance(args: argparse.Namespace) -> int:
    """`aios finance recover|invariants`: cold-start recovery and proof."""
    from core.financial_recovery import CapitalMode, FinancialRecovery
    from core.safety_plane import SafetyPlane

    store = _open_financial_store(args)
    try:
        if args.finance_command == "invariants":
            invariants = store.verify_invariants()
            for check in invariants.checks:
                flag = "OK  " if check.ok else "FAIL"
                print(f"  {flag} {check.name} {check.detail}".rstrip())
            print("INVARIANTS OK" if invariants.ok else "INVARIANTS VIOLATED")
            return 0 if invariants.ok else 1

        try:
            mode = CapitalMode(args.mode.upper())
        except ValueError:
            print(f"unknown capital mode {args.mode!r}", file=sys.stderr)
            return 2
        report = FinancialRecovery(
            store,
            account_id=args.account,
            requested_mode=mode,
            safety=SafetyPlane(store, account_id=args.account),
        ).run()
        print(json.dumps(report.as_dict(), indent=2, default=str))
        return 0 if report.execution_permitted else 1
    finally:
        store.close()


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

    p_events = sub.add_parser("events", help="durable event recovery: read log after cursor")
    p_events.add_argument("--db", default="data/aios.db")
    p_events.add_argument("--after", type=int, default=0)
    p_events.add_argument("--limit", type=int, default=50)
    p_events.add_argument("--kind", default="", help="filter by kind prefix (e.g. aios.platform.)")

    p_tail = sub.add_parser(
        "tail", help="independent consumer process: follow the durable log"
    )
    p_tail.add_argument("--db", default="data/aios.db")
    p_tail.add_argument("--after", type=int, default=0)
    p_tail.add_argument("--batch", type=int, default=200)
    p_tail.add_argument("--poll-interval", type=float, default=0.25)
    p_tail.add_argument("--json", action="store_true", help="JSON lines output")
    p_tail.add_argument(
        "--follow", action="store_true", help="keep polling for new events (long-running)"
    )
    p_tail.add_argument(
        "--state-file",
        default="",
        help="persist the cursor here so restarts resume exactly once",
    )

    def _store_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dsn", default="", help="PostgreSQL DSN (empty = local SQLite)")
        p.add_argument("--sqlite", default="data/financial.db", help="SQLite path")

    p_db = sub.add_parser("db", help="versioned financial schema: status | migrate")
    db_sub = p_db.add_subparsers(dest="db_command", required=True)
    for name, helptext in (
        ("status", "report applied vs required schema version"),
        ("migrate", "apply pending migrations (explicit, audited)"),
    ):
        child = db_sub.add_parser(name, help=helptext)
        _store_args(child)

    p_fin = sub.add_parser(
        "finance", help="financial plane: cold-start recovery | invariant proof"
    )
    fin_sub = p_fin.add_subparsers(dest="finance_command", required=True)
    p_rec = fin_sub.add_parser("recover", help="run the cold-start recovery sequence")
    _store_args(p_rec)
    p_rec.add_argument("--account", default="default")
    p_rec.add_argument(
        "--mode",
        default="PAPER",
        help="requested capital mode (AUTONOMOUS_LIVE is never granted here)",
    )
    p_inv = fin_sub.add_parser("invariants", help="verify financial invariants")
    _store_args(p_inv)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers: dict[str, Any] = {
        "boot": cmd_boot,
        "replay": cmd_replay,
        "summary-json": cmd_summary_json,
        "serve": cmd_serve,
        "events": cmd_events,
        "tail": cmd_tail,
        "db": cmd_db,
        "finance": cmd_finance,
    }
    return int(handlers[args.command](args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
