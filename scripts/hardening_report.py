"""Hardening pass: throughput measurement + security self-audit checklist.

Run:  python scripts/hardening_report.py
Writes research/benchmarks/hardening_report.json with honest numbers.
"""

import asyncio
import json
import pathlib
import sys
import tempfile
import time
from collections.abc import Coroutine
from typing import Any, TypeVar

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from simulation.generate_golden_data import write_dataset  # noqa: E402
from simulation.replay_runner import ReplayRunner  # noqa: E402


def measure_throughput(bars: int = 400) -> dict[str, float]:
    d = pathlib.Path(tempfile.mkdtemp())
    write_dataset(d / "g", symbols=["BTC/USD"], total_bars=bars)
    csv_path = d / "g" / "BTC_USD_1d.csv"

    started = time.perf_counter()
    runner = ReplayRunner({"BTC/USD": csv_path}, d / "perf.db")
    summary = asyncio_run(runner.run())
    elapsed = time.perf_counter() - started
    return {
        "bars": bars,
        "elapsed_s": round(elapsed, 3),
        "bars_per_second": round(bars / elapsed, 1),
        "trades": summary.trades_closed,
        "events_logged": summary.events_logged,
        "chain_valid": summary.chain_valid,
    }


_T = TypeVar("_T")


def asyncio_run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(coro)


SECURITY_CHECKLIST = [
    {"item": "secrets only via env (pydantic-settings, repr=False)", "status": "implemented"},
    {"item": ".env gitignored; .env.example committed without values", "status": "implemented"},
    {
        "item": "no API keys in code paths; adapters require explicit env opt-in",
        "status": "implemented",
    },
    {
        "item": "live execution gated by AIOS_ALLOW_LIVE_EXECUTION + testnet default",
        "status": "implemented",
    },
    {"item": "audit log hash-chained; tamper pinpointed in tests", "status": "implemented"},
    {"item": "lockout survives restart until human reset w/ operator id", "status": "implemented"},
    {
        "item": "topic-level ACLs enforced via ACLBus (mechanism shipped; per-agent wiring pending)",
        "status": "partial",
    },
    {
        "item": "dependency pinning (requirements.txt) + no known vulnerable pins at audit date",
        "status": "implemented",
    },
]


def main() -> None:
    perf = measure_throughput()
    report = {
        "date_note": "numbers recorded from THIS machine/run - not portable claims",
        "performance": perf,
        "security_checklist": SECURITY_CHECKLIST,
    }
    out_dir = pathlib.Path("research/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "hardening_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
