"""V1-A.2 multi-process concurrency: independent OS processes, not threads.

Every test here spawns genuinely separate Python processes that race on the same
financial store, aligned on a shared wall-clock barrier so the race is real. A
thread-level mutex can make two threads look safe while two processes race
straight through it, so threads are not accepted as evidence here.

What must survive:

- two processes applying the SAME broker execution,
- two processes transitioning ONE order,
- two outbox workers claiming the same backlog,
- concurrent cash reservations against a limited balance.

Both tiers are covered. The SQLite matrix always runs; the PostgreSQL matrix runs
when ``AIOS_TEST_PG_DSN`` is set (it is the tier where process-level locking is
actually load-bearing).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parent / "_v1a2_worker.py"
pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_postgres(reset_postgres: str) -> None:
    """Start the PostgreSQL matrix from a clean, migrated database.

    Requested from ``conftest``; it is a no-op when no DSN is configured, and
    it only truncates once per session.
    """


def run_workers(
    backend: str,
    target: str,
    invocations: list[tuple[str, dict[str, str]]],
    *,
    barrier_seconds: float = 1.0,
    timeout: float = 120.0,
) -> list[dict]:
    """Run every invocation concurrently, released together at one instant."""
    start_at = time.time() + barrier_seconds
    commands: list[list[str]] = []
    for mode, params in invocations:
        command = [
            sys.executable,
            str(WORKER),
            "--backend",
            backend,
            "--db",
            target,
            "--mode",
            mode,
            "--start-at",
            f"{start_at:.3f}",
        ]
        for key, value in params.items():
            command += ["--arg", f"{key}={value}"]
        commands.append(command)

    def _launch(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )

    with ThreadPoolExecutor(max_workers=len(commands)) as pool:
        completed = list(pool.map(_launch, commands))

    results: list[dict] = []
    for command, proc in zip(commands, completed, strict=True):
        if proc.returncode != 0:
            raise AssertionError(
                f"worker failed ({proc.returncode}): {' '.join(command[-6:])}\n"
                f"stdout={proc.stdout}\nstderr={proc.stderr[-2000:]}"
            )
        results.append(json.loads(proc.stdout or "{}"))
    return results


def _setup(backend: str, target: str, **extra: str) -> dict:
    # A client order id is a global idempotency key, so it must be unique per
    # test as well as per account; otherwise a rerun against the shared
    # PostgreSQL database would hand back the previous run's order.
    extra.setdefault("client_order_id", f"{extra.get('account', 'default')}-ord")
    return run_workers(backend, target, [("setup", extra)], barrier_seconds=0.0)[0]


# ---------------------------------------------------------------- fixtures


@pytest.fixture(params=["sqlite", "postgres"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[str, str]:
    """Both store tiers; PostgreSQL skips without a DSN, as elsewhere in the suite."""
    if request.param == "postgres":
        dsn = os.environ.get("AIOS_TEST_PG_DSN", "")
        if not dsn:
            pytest.skip("set AIOS_TEST_PG_DSN to run the PostgreSQL concurrency matrix")
        return "postgres", dsn
    return "sqlite", str(tmp_path / "financial.db")


# ------------------------------------------------- same execution, two processes


def test_two_processes_cannot_apply_one_execution_twice(backend) -> None:
    name, target = backend
    account = f"acct-{name}-dup-{os.getpid()}"
    order = _setup(name, target, account=account, order="1", quantity="10")
    order_id = order["order_id"]

    results = run_workers(
        name,
        target,
        [
            (
                "apply-fill",
                {
                    "order_id": order_id,
                    "fill_id": f"fill-{account}",
                    "exec_id": f"exec-{account}",
                    "account": account,
                    "quantity": "1",
                    "price": "100",
                },
            )
        ]
        * 2,
    )
    applied = [r["applied"] for r in results]
    assert applied.count(True) == 1, f"exactly one process may apply: {applied}"
    assert applied.count(False) == 1
    assert all(r["fills"] == 1 for r in results)

    invariants = run_workers(name, target, [("invariants", {})], barrier_seconds=0.0)[0]
    assert invariants["ok"] is True, invariants["failures"]


def test_two_processes_cannot_overfill_one_order(backend) -> None:
    """Distinct executions but more quantity than the order allows."""
    name, target = backend
    account = f"acct-{name}-over-{os.getpid()}"
    order = _setup(name, target, account=account, order="1", quantity="1")
    order_id = order["order_id"]

    results = run_workers(
        name,
        target,
        [
            (
                "apply-fill",
                {
                    "order_id": order_id,
                    "fill_id": f"fill-a-{account}",
                    "exec_id": f"exec-a-{account}",
                    "account": account,
                    "quantity": "0.6",
                    "price": "100",
                },
            ),
            (
                "apply-fill",
                {
                    "order_id": order_id,
                    "fill_id": f"fill-b-{account}",
                    "exec_id": f"exec-b-{account}",
                    "account": account,
                    "quantity": "0.6",
                    "price": "100",
                },
            ),
        ],
    )
    # One 0.6 fill is applied; the other must be *rejected* rather than
    # truncated, because 0.6 is not what the remaining 0.4 authorised.
    assert [r["applied"] for r in results].count(True) == 1, results
    rejected = next(r for r in results if not r["applied"])
    assert rejected["error"].startswith("OverFill"), rejected

    filled = max(r["filled_quantity"] for r in results)
    assert filled <= 1.0 + 1e-9, f"order overfilled: {filled}"

    invariants = run_workers(name, target, [("invariants", {})], barrier_seconds=0.0)[0]
    assert invariants["ok"] is True, invariants["failures"]
    assert "no_overfilled_orders" not in invariants["failures"]


# --------------------------------------------------- one order, two transitions


def test_two_processes_cannot_double_advance_one_order(backend) -> None:
    name, target = backend
    account = f"acct-{name}-trans-{os.getpid()}"
    order = _setup(name, target, account=account, order="1", quantity="10")
    order_id = order["order_id"]

    results = run_workers(
        name,
        target,
        [
            (
                "transition",
                {
                    "order_id": order_id,
                    "to_status": "FILLED",
                    "actor": "worker-a",
                },
            ),
            (
                "transition",
                {
                    "order_id": order_id,
                    "to_status": "FILLED",
                    "actor": "worker-b",
                },
            ),
        ],
    )
    outcomes = sorted(r["ok"] for r in results)
    # The state machine allows exactly one winner: FILLED is terminal, so the
    # second process is rejected no matter which order the two are serialised in.
    assert outcomes == [False, True], results
    loser = next(r for r in results if not r["ok"])
    assert loser["error"] == "InvalidOrderTransition", loser
    winner = next(r for r in results if r["ok"])
    assert winner["version"] == 3, winner  # PENDING_NEW(v1) -> ACCEPTED(v2) -> FILLED(v3)

    invariants = run_workers(name, target, [("invariants", {})], barrier_seconds=0.0)[0]
    assert invariants["ok"] is True, invariants["failures"]


def test_two_processes_cannot_illegally_close_a_terminal_order(backend) -> None:
    name, target = backend
    account = f"acct-{name}-term-{os.getpid()}"
    order = _setup(name, target, account=account, order="1", quantity="10")
    order_id = order["order_id"]

    first = run_workers(
        name,
        target,
        [("transition", {"order_id": order_id, "to_status": "CANCELLED", "actor": "w"})],
        barrier_seconds=0.0,
    )[0]
    assert first["ok"] is True

    second = run_workers(
        name,
        target,
        [("transition", {"order_id": order_id, "to_status": "FILLED", "actor": "w"})],
        barrier_seconds=0.0,
    )[0]
    assert second["ok"] is False
    assert second["error"] == "InvalidOrderTransition"
    assert second["status"] == "CANCELLED"


# ----------------------------------------------------- outbox claim disjointness


def test_two_outbox_workers_claim_disjoint_batches(backend) -> None:
    name, target = backend
    account = f"acct-{name}-outbox-{os.getpid()}"
    # Start from a known-empty outbox. The PostgreSQL tier is shared across the
    # session, so orphaned events from earlier tests would otherwise be older
    # than this test's events and be claimed first, in place of the ones the
    # assertions are about. Draining is exactly what a publisher does.
    drained = run_workers(name, target, [("publish-outbox", {})], barrier_seconds=0.0)[0]
    assert drained["backlog"] == 0, drained

    # Each seeded order enqueues one order_requested event.
    for index in range(4):
        _setup(name, target, account=account, order="1", client_order_id=f"{account}-o-{index}")

    # Each worker is bounded to 2 of the 4 events, so *both* must claim work for
    # the backlog to drain. With an unbounded limit the winner-takes-all outcome
    # is legal but says nothing about contention, which is what this drill is for.
    results = run_workers(
        name,
        target,
        [
            ("claim-outbox", {"worker": "w1", "limit": "2"}),
            ("claim-outbox", {"worker": "w2", "limit": "2"}),
        ],
    )
    first, second = (set(r["claimed"]) for r in results)
    assert not (first & second), f"two workers claimed the same event: {first & second}"
    assert len(first) + len(second) == sum(r["count"] for r in results)
    # 4 events, 2 workers x limit 2: every event must be claimed exactly once, so
    # the backlog drains regardless of which process wins the race.
    assert len(first) + len(second) == 4, f"backlog not fully claimed: {results}"

    # Nothing may be left PENDING (a third worker finds an empty queue), yet the
    # backlog must still count all four events: claimed work is in flight, not
    # lost. Both readings are race-free after the two claimers have exited.
    left_behind, health = run_workers(
        name,
        target,
        [("claim-outbox", {"worker": "w3", "limit": "10"}), ("health", {})],
        barrier_seconds=0.0,
    )
    assert left_behind["claimed"] == [], f"unclaimed events remain: {left_behind}"
    assert health["outbox_backlog"] == 4, health


# ------------------------------------------------------- concurrent reservations


def test_concurrent_reservations_cannot_overspend_cash(backend) -> None:
    name, target = backend
    account = f"acct-{name}-res-{os.getpid()}"
    _setup(name, target, account=account, opening_minor="1000")

    # Five processes each try to reserve 300 of 1000: at most three may succeed.
    invocations = [
        (
            "reserve",
            {"account": account, "amount_minor": "300", "reservation_id": f"r-{i}"},
        )
        for i in range(5)
    ]
    results = run_workers(name, target, invocations)
    granted = [r for r in results if r["ok"]]
    assert len(granted) <= 3, f"over-reserved: {len(granted)} grants against 1000/300"
    assert all(r.get("error") in (None, "InsufficientCash") for r in results), results

    health = run_workers(name, target, [("health", {})], barrier_seconds=0.0)[0]
    assert health["reachable"] is True

    invariants = run_workers(name, target, [("invariants", {})], barrier_seconds=0.0)[0]
    assert invariants["ok"] is True, invariants["failures"]
    assert "reservations_within_settled_cash" not in invariants["failures"]
