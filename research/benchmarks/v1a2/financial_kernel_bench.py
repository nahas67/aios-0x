"""V1-A.2 performance: practical institutional numbers, measured not assumed.

The mission is explicit that correctness outranks throughput and that HFT-grade
optimisation is premature. So this harness measures exactly the operations the
V1-A.2 completion standard names — order transaction latency, fill application
latency, IBOR snapshot latency, outbox throughput, JetStream publication,
reconciliation runtime, PostgreSQL contention — and records the results rather
than asserting a target.

What it does *not* do is pretend an unmeasured layer is fast. Each tier reports
its own block, and a tier whose service is unavailable is recorded with
``status: "unavailable"`` and a reason. A benchmark that silently skips the
database tier and prints one green number is worse than no benchmark.

Usage:
    python research/benchmarks/v1a2/financial_kernel_bench.py
    python research/benchmarks/v1a2/financial_kernel_bench.py \\
        --postgres "postgresql://aios:testpass123@127.0.0.1:5433/aios_test" \\
        --nats "nats://127.0.0.1:54222" --reps 5

Writes ``research/benchmarks/v1a2/financial_kernel.json``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from communities.c5_execution.oms import DurableOrderManager  # noqa: E402
from communities.c5_execution.reconciliation import (  # noqa: E402
    BrokerSnapshot,
    ReconciliationEngine,
    ReconciliationWindow,
)
from core.financial_kernel import (  # noqa: E402
    CashPosting,
    CashReservation,
    Fill,
    ReconciliationMode,
    SqliteFinancialStore,
)
from core.ibor import InvestmentBookOfRecord  # noqa: E402
from schemas.contracts import OrderSide  # noqa: E402

OUT_PATH = ROOT / "research" / "benchmarks" / "v1a2" / "financial_kernel.json"

#: Reassigned by ``main`` to a run-unique value. The PostgreSQL tier is a real
#: database that persists between runs, so a fixed account or idempotency key
#: would make the second run collide with the first run's state (the order would
#: already be PARTIALLY_FILLED and could not be accepted again).
ACCOUNT = "bench"


# -------------------------------------------------------------------- helpers


def percentiles(samples: list[float]) -> dict[str, float]:
    """p50/p95/p99 plus mean and bounds, in the unit the caller supplied."""
    if not samples:
        return {}
    ordered = sorted(samples)

    def pick(fraction: float) -> float:
        index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
        return ordered[index]

    return {
        "n": len(ordered),
        "mean": round(statistics.fmean(ordered), 4),
        "p50": round(pick(0.50), 4),
        "p95": round(pick(0.95), 4),
        "p99": round(pick(0.99), 4),
        "min": round(ordered[0], 4),
        "max": round(ordered[-1], 4),
    }


def seed(store: Any, account: str, opening_minor: int = 10**12) -> None:
    """Fund an account; the counterparty leg keeps every transaction balanced."""
    store.post_cash(
        [
            CashPosting(transaction_id=f"bench-seed:{account}", account_id=account, amount_minor=opening_minor),
            CashPosting(
                transaction_id=f"bench-seed:{account}",
                account_id="counterparty",
                amount_minor=-opening_minor,
            ),
        ]
    )


def make_order(store: Any, account: str, index: int, quantity: float = 1_000_000.0) -> Any:
    oms = DurableOrderManager(store, account_id=account)
    prepared = oms.prepare_order(
        client_order_id=f"{account}-bench-{index}",
        strategy_id="bench-strategy",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=quantity,
    )
    return oms.accept(prepared.internal_order_id)


def timed(call: Callable[[], Any]) -> float:
    started = time.perf_counter()
    call()
    return (time.perf_counter() - started) * 1000.0


# ----------------------------------------------------------------- benchmarks


def bench_order_transaction(store: Any, account: str, count: int) -> dict[str, float]:
    """Write-ahead submit plus the venue acknowledgement, in milliseconds."""
    seed(store, account)
    samples: list[float] = []
    for index in range(count):
        oms = DurableOrderManager(store, account_id=account)
        order = oms.prepare_order(
            client_order_id=f"{account}-order-{index}",
            strategy_id="bench-strategy",
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1000.0,
        )
        # partial binds THIS iteration's objects at call-creation time, so the
        # measured call cannot accidentally close over a later loop value.
        samples.append(timed(partial(oms.accept, order.internal_order_id)))
    return percentiles(samples)


def bench_fill_application(store: Any, account: str, count: int) -> dict[str, float]:
    """One fill application (fill row + order state + position + outbox), ms."""
    seed(store, account)
    order = make_order(store, account, 0, quantity=float(count) + 1.0)
    samples: list[float] = []
    for index in range(count):
        fill = Fill(
            fill_id=f"{account}-fill-{index}",
            order_id=order.internal_order_id,
            broker_execution_id=f"{account}-exec-{index}",
            account_id=account,
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=50_000.0,
            fee=0.01,
        )
        samples.append(timed(partial(store.apply_fill, fill)))
    return percentiles(samples)


def bench_ibor_snapshot(store: Any, count: int) -> dict[str, float]:
    """Book of Record projection over the live rows, in milliseconds."""
    book = InvestmentBookOfRecord(store, account_id=ACCOUNT)
    samples = [timed(book.snapshot) for _ in range(count)]
    return percentiles(samples)


def bench_reconciliation(store: Any, count: int) -> dict[str, float]:
    """One durable reconciliation pass (positions-only venue coverage), ms."""
    engine = ReconciliationEngine(store, account_id=ACCOUNT)
    venue = {"BTC/USD": 1.0}

    def one_pass() -> None:
        engine.reconcile(
            BrokerSnapshot(
                ReconciliationWindow(
                    mode=ReconciliationMode.FULL_SNAPSHOT,
                    account_id=ACCOUNT,
                    broker="bench-venue",
                    adapter_version="bench-1.0",
                    covers_orders=False,
                    covers_executions=False,
                    covers_positions=True,
                ),
                positions=venue,
            )
        )

    return percentiles([timed(one_pass) for _ in range(count)])


def bench_outbox_throughput(store: Any, batches: int, batch_size: int = 200) -> dict[str, Any]:
    """Claim + publish committed events; events per second, end to end."""
    # Top up the queue so each batch has work to claim.
    for index in range(batches * batch_size):
        make_order(store, ACCOUNT, 100_000 + index, quantity=1.0)
    started = time.perf_counter()
    published = 0
    for _ in range(batches):
        for event in store.claim_outbox("bench-worker", limit=batch_size):
            store.mark_published(event.event_id)
            published += 1
    elapsed = time.perf_counter() - started
    return {
        "published": published,
        "seconds": round(elapsed, 4),
        "events_per_sec": round(published / elapsed, 1) if elapsed > 0 else None,
        "remaining_backlog": store.outbox_backlog(),
    }


def bench_reservation(store: Any, account: str, count: int) -> dict[str, float]:
    """Reserve + release one cash amount (advisory-lock serialised on PG)."""
    seed(store, account, opening_minor=10**12)
    samples: list[float] = []

    def one() -> None:
        reservation = store.reserve_cash(
            CashReservation(account_id=account, currency="USD", amount_minor=1000, reason="bench")
        )
        store.release_cash(reservation.reservation_id)

    for _ in range(count):
        samples.append(timed(one))
    return percentiles(samples)


def bench_postgres_contention(dsn: str, workers: int, per_worker: int, tag: str) -> dict[str, Any]:
    """K independent server backends racing on one shared order.

    Each worker opens its own connection (a real PostgreSQL backend process) and
    applies fills to the *same* order, which is exactly where the row lock is
    load-bearing. The measurement is throughput plus how many applications
    actually landed: a run where every worker succeeded would mean the lock did
    nothing, so the applied count is recorded as part of the result.

    Process-level racing is verified separately by
    ``tests/test_v1a2_concurrency.py``; this figure is about database-side
    contention between backends.
    """
    from core.pg_financial_store import PostgresFinancialStore

    setup = PostgresFinancialStore(dsn, auto_migrate=True)
    try:
        seed(setup, ACCOUNT)
        order = make_order(setup, ACCOUNT, 99_999, quantity=float(workers * per_worker) + 1.0)
    finally:
        setup.close()

    applied = [0] * workers
    errors: list[str] = []
    barrier = threading.Barrier(workers)
    order_id = order.internal_order_id

    def worker(index: int) -> None:
        store = PostgresFinancialStore(dsn, auto_migrate=True)
        try:
            barrier.wait(timeout=30)  # release every backend at one instant
            for step in range(per_worker):
                try:
                    ok = store.apply_fill(
                        Fill(
                            fill_id=f"pgbench-{tag}-{index}-{step}",
                            order_id=order_id,
                            broker_execution_id=f"pgbench-exec-{tag}-{index}-{step}",
                            account_id=ACCOUNT,
                            symbol="BTC/USD",
                            side=OrderSide.BUY,
                            quantity=1.0,
                            price=50_000.0,
                        )
                    )
                    if ok:
                        applied[index] += 1
                except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                    errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            store.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started

    total = sum(applied)
    verify = PostgresFinancialStore(dsn, auto_migrate=True)
    try:
        fills = len(verify.fills(order_id))
        invariants_ok = verify.verify_invariants().ok
    finally:
        verify.close()

    return {
        "workers": workers,
        "per_worker": per_worker,
        "targeted": workers * per_worker,
        "applied": total,
        "applied_per_worker": applied,
        "seconds": round(elapsed, 4),
        "fills_per_sec": round(total / elapsed, 1) if elapsed > 0 else None,
        "fills_persisted": fills,
        "invariants_ok": invariants_ok,
        "errors": errors[:5],
        "error_count": len(errors),
        "note": (
            "workers are independent PostgreSQL backends racing on one order row; "
            "process-level races are covered by tests/test_v1a2_concurrency.py"
        ),
    }


async def _jetstream_run(url: str, count: int) -> dict[str, Any]:
    from core.event_bus import EventTopic
    from core.jetstream_bus import JetStreamBus
    from schemas.contracts import PriceData

    bus = JetStreamBus(url)
    await bus.connect()
    try:
        # Distinct payloads per iteration on purpose. ``publish`` derives the
        # ``Nats-Msg-Id`` from the payload hash, so re-sending one byte-identical
        # payload would be *correctly* deduplicated by the stream's duplicate
        # window: the loop would report a high publish rate while the broker
        # stored a single message. The dedup counter is reported below so the
        # reader can confirm nothing was silently collapsed.
        payloads = [
            PriceData(open=1.0, high=1.0, low=1.0, close=1.0, volume=float(index + 1))
            for index in range(count)
        ]
        before = bus.deduplicated
        started = time.perf_counter()
        for payload in payloads:
            await bus.publish(EventTopic.DATA_ACQUIRED, payload)
        elapsed = time.perf_counter() - started
        publish_rate = count / elapsed if elapsed > 0 else None
        deduplicated = bus.deduplicated - before

        # Consumer lag after the burst: the honest "is the platform keeping up?"
        # reading. None when the consumer cannot be inspected (or does not exist
        # yet, which is the normal case for a freshly created durable).
        lag: int | None = None
        lag_fn = getattr(bus, "consumer_lag", None)
        if callable(lag_fn):
            try:
                lag = await lag_fn("bench")
            except Exception:  # noqa: BLE001 - unknown stays unknown
                lag = None
        return {
            "status": "measured",
            "messages": count,
            "seconds": round(elapsed, 4),
            "msg_per_sec": round(publish_rate, 1) if publish_rate else None,
            "published_counter": bus.published,
            "deduplicated": deduplicated,
            "publish_failures": bus.publish_failures,
            "consumer_lag": lag,
            "stored_distinct_payloads": count - deduplicated,
            "health": bus.health(),
        }
    finally:
        await bus.stop()


def bench_jetstream(url: str | None, count: int) -> dict[str, Any]:
    if not url:
        return {
            "status": "unavailable",
            "reason": "no NATS URL supplied (--nats / AIOS_TEST_NATS_URL)",
        }
    try:
        return asyncio.run(_jetstream_run(url, count))
    except Exception as exc:  # noqa: BLE001 - record the failure honestly
        return {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}


def bench_tier(name: str, store: Any, args: argparse.Namespace) -> dict[str, Any]:
    tier: dict[str, Any] = {"backend": name}
    try:
        tier["order_transaction_ms"] = bench_order_transaction(store, ACCOUNT, args.orders)
        tier["fill_application_ms"] = bench_fill_application(store, ACCOUNT, args.fills)
        tier["cash_reserve_release_ms"] = bench_reservation(store, ACCOUNT, args.reservations)
        tier["ibor_snapshot_ms"] = bench_ibor_snapshot(store, args.snapshots)
        tier["reconciliation_ms"] = bench_reconciliation(store, args.reconciliations)
        tier["outbox"] = bench_outbox_throughput(store, batches=args.outbox_batches)
        tier["invariants_ok"] = store.verify_invariants().ok
    except Exception as exc:  # noqa: BLE001
        tier["status"] = "failed"
        tier["error"] = f"{type(exc).__name__}: {exc}"
        return tier
    tier["status"] = "measured"
    return tier


# ----------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=3, help="repetitions per tier")
    parser.add_argument("--postgres", default=os.environ.get("AIOS_TEST_PG_DSN", ""))
    parser.add_argument("--nats", default=os.environ.get("AIOS_TEST_NATS_URL", ""))
    parser.add_argument("--orders", type=int, default=300)
    parser.add_argument("--fills", type=int, default=300)
    parser.add_argument("--reservations", type=int, default=150)
    parser.add_argument("--snapshots", type=int, default=100)
    parser.add_argument("--reconciliations", type=int, default=50)
    parser.add_argument("--outbox-batches", type=int, default=5)
    parser.add_argument("--contention-workers", type=int, default=4)
    parser.add_argument("--contention-per-worker", type=int, default=50)
    parser.add_argument("--jetstream-messages", type=int, default=2000)
    args = parser.parse_args(argv)

    global ACCOUNT
    started = time.time()
    # Unique per invocation: the PostgreSQL tier is a real, persistent database.
    run_tag = f"{int(started)}-{os.getpid()}"
    ACCOUNT = f"bench-{run_tag}"
    result: dict[str, Any] = {
        "phase": "V1-A.2",
        "harness": "research/benchmarks/v1a2/financial_kernel_bench.py",
        "run_tag": run_tag,
        "account": ACCOUNT,
        "note": (
            "Institutional V1 numbers, single node, correctness first. Latencies are "
            "milliseconds (mean/p50/p95/p99). Run on a shared developer workstation, "
            "not a dedicated benchmark host."
        ),
        "config": {
            "orders": args.orders,
            "fills": args.fills,
            "reservations": args.reservations,
            "snapshots": args.snapshots,
            "reconciliations": args.reconciliations,
            "outbox_batches": args.outbox_batches,
            "contention_workers": args.contention_workers,
            "contention_per_worker": args.contention_per_worker,
            "jetstream_messages": args.jetstream_messages,
            "reps": args.reps,
        },
        "tiers": {},
    }

    # --- SQLite: the hermetic/development tier.
    sqlite_runs: list[dict[str, Any]] = []
    for rep in range(args.reps):
        with tempfile.TemporaryDirectory() as tmp:
            store = SqliteFinancialStore(Path(tmp) / f"bench-{rep}.db")
            try:
                sqlite_runs.append(bench_tier("sqlite", store, args))
            finally:
                store.close()
    result["tiers"]["sqlite"] = sqlite_runs[-1] if sqlite_runs else {}
    result["tiers"]["sqlite"]["reps"] = len(sqlite_runs)
    result["tiers"]["sqlite"]["fill_application_ms_p50_by_rep"] = [
        r.get("fill_application_ms", {}).get("p50") for r in sqlite_runs
    ]

    # --- PostgreSQL: the production tier, plus contention between backends.
    if args.postgres:
        from core.pg_financial_store import PostgresFinancialStore

        # Named separately from the SQLite tier: the two stores are different
        # types, and the benchmark must never blur which one produced a number.
        pg_store = PostgresFinancialStore(args.postgres, auto_migrate=True)
        try:
            result["tiers"]["postgres"] = bench_tier("postgres", pg_store, args)
        finally:
            pg_store.close()
        result["tiers"]["postgres"]["contention"] = bench_postgres_contention(
            args.postgres, args.contention_workers, args.contention_per_worker, run_tag
        )
    else:
        result["tiers"]["postgres"] = {
            "status": "unavailable",
            "reason": "no PostgreSQL DSN supplied (--postgres / AIOS_TEST_PG_DSN)",
        }

    # --- JetStream: the durable transport.
    result["jetstream"] = bench_jetstream(args.nats, args.jetstream_messages)

    result["wall_seconds"] = round(time.time() - started, 2)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
