"""Standalone worker process for the V1-A.2 concurrency and chaos tests.

Concurrency verification must use genuinely independent processes, not threads:
a Python-level mutex can make two threads look safe while two OS processes race
straight through it. This worker is spawned with ``subprocess`` by
``tests/test_v1a2_concurrency.py``.

Every mode prints a single JSON object on stdout and exits non-zero only for an
unexpected failure, so the parent can assert on outcomes rather than log noise.

Usage:
    python tests/_v1a2_worker.py --backend sqlite --db <path> --mode apply-fill \
        --arg fill_id=f1 --arg exec_id=e1 --arg client_order_id=o1 \
        --start-at 1700000000.5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # run as a script, not a module
    sys.path.insert(0, str(ROOT))

from core.financial_kernel import (  # noqa: E402
    CashPosting,
    CashReservation,
    Fill,
    FinancialStoreError,
    OverFill,
    SqliteFinancialStore,
    StaleOrderVersion,
)
from schemas.contracts import OrderSide, OrderStatus  # noqa: E402


def open_store(backend: str, target: str):
    if backend == "postgres":
        from core.pg_financial_store import PostgresFinancialStore

        return PostgresFinancialStore(target, auto_migrate=True)
    return SqliteFinancialStore(target)


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, default=str))
    sys.stdout.flush()


def wait_for_start(start_at: float | None) -> None:
    """Line every worker up on a common wall-clock instant.

    Without a barrier the first process usually finishes before the second even
    starts, which silently turns a concurrency test into a sequential one.
    """
    if start_at is None:
        return
    while time.time() < start_at:
        time.sleep(0.001)


def parse_args(argv: list[str] | None) -> tuple[argparse.Namespace, dict[str, str]]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("sqlite", "postgres"), default="sqlite")
    parser.add_argument("--db", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--arg", action="append", default=[])
    parser.add_argument("--start-at", type=float, default=None)
    args = parser.parse_args(argv)
    params: dict[str, str] = {}
    for item in args.arg:
        key, _, value = item.partition("=")
        params[key] = value
    return args, params


def main(argv: list[str] | None = None) -> int:
    args, p = parse_args(argv)
    store = open_store(args.backend, args.db)
    try:
        wait_for_start(args.start_at)
        handler = MODES[args.mode]
        emit(handler(store, p))
        return 0
    finally:
        store.close()


# --------------------------------------------------------------------- modes


def mode_setup(store, p: dict[str, str]) -> dict:
    """Create the schema, seed cash and (optionally) one accepted order."""
    account = p.get("account", "default")
    opening = int(p.get("opening_minor", "1000000"))
    store.post_cash(
        [
            CashPosting(
                transaction_id=f"seed:{account}", account_id=account, amount_minor=opening
            ),
            CashPosting(
                transaction_id=f"seed:{account}", account_id="counterparty", amount_minor=-opening
            ),
        ]
    )
    if p.get("order") == "1":
        from communities.c5_execution.oms import DurableOrderManager

        oms = DurableOrderManager(store, account_id=account)
        order = oms.prepare_order(
            client_order_id=p.get("client_order_id", "ord-1"),
            strategy_id="s1",
            symbol=p.get("symbol", "BTC/USD"),
            side=OrderSide.BUY,
            quantity=float(p.get("quantity", "10")),
        )
        accepted = oms.accept(order.internal_order_id)
        return {
            "order_id": accepted.internal_order_id,
            "client_order_id": accepted.client_order_id,
            "cash_minor": store.cash_balance_minor(account, "USD"),
        }
    return {"cash_minor": store.cash_balance_minor(account, "USD")}


def mode_apply_fill(store, p: dict[str, str]) -> dict:
    """Apply one venue execution; reports whether THIS process applied it.

    A fill that would exceed the authorized quantity is *rejected*, not silently
    truncated: it means the venue and the plan disagree, which is exactly the
    kind of anomaly that must surface. The rejection is reported rather than
    raised so the parent can assert on both racing outcomes.
    """
    try:
        applied = store.apply_fill(
            Fill(
                fill_id=p["fill_id"],
                order_id=p["order_id"],
                broker_execution_id=p["exec_id"],
                account_id=p.get("account", "default"),
                symbol=p.get("symbol", "BTC/USD"),
                side=OrderSide.BUY,
                quantity=float(p.get("quantity", "1")),
                price=float(p.get("price", "100")),
            )
        )
        error = None
    except OverFill as exc:
        applied = False
        error = f"{type(exc).__name__}: {exc}"
    return {
        "applied": applied,
        "error": error,
        "fills": len(store.fills(p["order_id"])),
        "filled_quantity": store.order(p["order_id"]).filled_quantity,  # type: ignore[union-attr]
    }


def mode_transition(store, p: dict[str, str]) -> dict:
    """Attempt one order transition; reports the outcome without raising."""
    try:
        order = store.transition_order(
            p["order_id"],
            OrderStatus(p["to_status"]),
            actor=p.get("actor", "worker"),
            reason="concurrency drill",
            expected_version=int(p["expected_version"]) if "expected_version" in p else None,
        )
        return {"ok": True, "status": str(order.status), "version": order.version}
    except (StaleOrderVersion, FinancialStoreError) as exc:
        current = store.order(p["order_id"])
        return {
            "ok": False,
            "error": type(exc).__name__,
            "detail": str(exc),
            "status": str(current.status) if current else None,
            "version": current.version if current else None,
        }


def mode_claim_outbox(store, p: dict[str, str]) -> dict:
    claimed = store.claim_outbox(p.get("worker", "w"), limit=int(p.get("limit", "100")))
    return {"claimed": [e.event_id for e in claimed], "count": len(claimed)}


def mode_publish_outbox(store, p: dict[str, str]) -> dict:
    """Claim and publish everything currently queued, returning the queue to empty.

    Tests that assert on an exact backlog need a known starting point. The
    PostgreSQL tier is shared across a whole session, so orphaned events from
    earlier tests would otherwise be older than the events under test and get
    claimed first. This is the same drain a publisher performs in production.
    """
    worker = p.get("worker", "drain")
    published = 0
    while True:
        batch = store.claim_outbox(worker, limit=100)
        if not batch:
            break
        for event in batch:
            store.mark_published(event.event_id)
            published += 1
    return {"published": published, "backlog": store.outbox_backlog()}


def mode_reserve(store, p: dict[str, str]) -> dict:
    """Attempt one cash reservation against a deliberately limited balance."""
    try:
        reservation = store.reserve_cash(
            CashReservation(
                account_id=p.get("account", "default"),
                currency="USD",
                amount_minor=int(p["amount_minor"]),
                reason="concurrency drill",
            )
        )
        return {"ok": True, "reservation_id": reservation.reservation_id}
    except FinancialStoreError as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}


def mode_invariants(store, p: dict[str, str]) -> dict:
    report = store.verify_invariants()
    return {
        "ok": report.ok,
        "failures": [c.name for c in report.failures()],
        "checks": len(report.checks),
    }


def mode_health(store, p: dict[str, str]) -> dict:
    return store.health()


MODES = {
    "setup": mode_setup,
    "apply-fill": mode_apply_fill,
    "transition": mode_transition,
    "claim-outbox": mode_claim_outbox,
    "publish-outbox": mode_publish_outbox,
    "reserve": mode_reserve,
    "invariants": mode_invariants,
    "health": mode_health,
}


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main())
