"""V1-A.2 API surface over the durable financial kernel.

Two things are being proven here, and they are different in kind:

1. **Visibility.** An operator can see the book of record, orders, fills, cash,
   reservations, invariants, outbox health and reconciliation state over HTTP.
   Every one of these endpoints must report ``available: false`` when the kernel
   is not wired rather than return a plausible-looking empty book (§75).

2. **Authority.** The only financial mutation reachable over HTTP is releasing a
   safety lockout, and that must obey the same server-resolved RBAC matrix as the
   rest of the control plane. A request body claiming ``role: ADMIN`` proves
   nothing; a VIEWER token must be refused even with a perfect body.

Requires no external services: SQLite store, real HTTP server on a random port.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from api.server import CommandCenterServer, ServerIdentity
from api.views import SystemSnapshotBuilder
from communities.c5_execution.oms import DurableOrderManager
from core.financial_kernel import (
    CashPosting,
    Fill,
    LockoutScope,
    SafetyLockout,
    SqliteFinancialStore,
)
from core.ibor import InvestmentBookOfRecord
from core.persistence import SqliteMemoryStore
from core.safety_plane import SafetyPlane
from schemas.contracts import OrderSide

pytestmark = pytest.mark.integration

VIEWER_TOKEN = "token-viewer"
OPERATOR_TOKEN = "token-operator"
RISK_ADMIN_TOKEN = "token-risk-admin"


def _request(method: str, url: str, token: str | None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return exc.code, {}


class KernelApi:
    """A real server over a real (if SQLite) financial kernel."""

    def __init__(
        self,
        port: int,
        store: SqliteFinancialStore,
        safety: SafetyPlane,
        audit: SqliteMemoryStore,
    ) -> None:
        self.port = port
        self.store = store
        self.safety = safety
        self.audit = audit

    def get(self, path: str, token: str | None = OPERATOR_TOKEN):
        return _request("GET", f"http://127.0.0.1:{self.port}{path}", token)

    def release(self, lockout_id: str, token: str | None, note: str = "reviewed by risk"):
        return _request(
            "POST",
            f"http://127.0.0.1:{self.port}/api/v1/financial/lockouts/{lockout_id}/release",
            token,
            {"note": note},
        )


def _serve(builder: SystemSnapshotBuilder) -> tuple[CommandCenterServer, int]:
    server = CommandCenterServer(
        builder,
        None,
        port=0,
        identity_map={
            VIEWER_TOKEN: ServerIdentity(operator_id="viewer-1", role="VIEWER"),
            OPERATOR_TOKEN: ServerIdentity(operator_id="operator-1", role="OPERATOR"),
            RISK_ADMIN_TOKEN: ServerIdentity(operator_id="risk-1", role="RISK_ADMIN"),
        },
    )
    server.start()
    time.sleep(0.2)
    return server, server.port


@pytest.fixture
def wired(tmp_path: Path) -> Iterator[KernelApi]:
    """A builder with the durable kernel wired in, exactly as the runner does it."""
    financial = SqliteFinancialStore(tmp_path / "financial.db")
    audit = SqliteMemoryStore(tmp_path / "audit.db")
    safety = SafetyPlane(financial, audit=audit, account_id="acct-1", broker="paper")
    ibor = InvestmentBookOfRecord(financial, account_id="acct-1")

    oms = DurableOrderManager(financial, account_id="acct-1", safety=safety)
    order = oms.prepare_order(
        client_order_id="api-order-1",
        strategy_id="momentum-1",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        quantity=2.0,
    )
    oms.accept(order.internal_order_id, broker_order_id="broker-42")
    oms.apply_fill(
        Fill(
            fill_id="fill-api-1",
            order_id=order.internal_order_id,
            broker_execution_id="exec-api-1",
            account_id="acct-1",
            symbol="BTC/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=100.0,
        )
    )

    builder = SystemSnapshotBuilder(
        store=audit,
        financial_store=financial,
        ibor=ibor,
        safety_plane=safety,
    )
    server, port = _serve(builder)
    try:
        yield KernelApi(port, financial, safety, audit)
    finally:
        server.stop()
        financial.close()
        audit.close()


@pytest.fixture
def unwired(tmp_path: Path) -> Iterator[KernelApi]:
    """A server whose builder has no durable kernel: must say so, not invent."""
    audit = SqliteMemoryStore(tmp_path / "audit.db")
    server, port = _serve(SystemSnapshotBuilder(store=audit))
    try:
        yield KernelApi(port, None, None, audit)  # type: ignore[arg-type]
    finally:
        server.stop()
        audit.close()


# --------------------------------------------------------------------- reads


def test_book_of_record_reports_nav_and_marked_positions(wired: KernelApi) -> None:
    status, body = wired.get("/api/v1/financial/ibor")
    assert status == 200
    assert body["available"] is True
    assert body["account_id"] == "acct-1"
    position = next(p for p in body["positions"] if p["symbol"] == "BTC/USD")
    assert position["quantity"] == pytest.approx(1.0)


def test_unmarked_position_reports_nav_unknown_not_invented(wired: KernelApi) -> None:
    """No mark provider is wired, so NAV must be null rather than guessed (§75)."""
    status, body = wired.get("/api/v1/financial/ibor")
    assert status == 200
    assert body["nav"] is None
    assert body["marks_complete"] is False


def test_positions_and_fills_reflect_the_fill_ledger(wired: KernelApi) -> None:
    status, positions = wired.get("/api/v1/financial/positions")
    assert status == 200
    assert positions["available"] is True
    assert positions["positions"][0]["quantity"] == pytest.approx(1.0)

    status, fills = wired.get("/api/v1/financial/fills")
    assert status == 200
    assert [f["fill_id"] for f in fills["fills"]] == ["fill-api-1"]
    assert fills["fills"][0]["broker_execution_id"] == "exec-api-1"


def test_order_detail_exposes_the_ledger_of_transitions_and_fills(
    wired: KernelApi,
) -> None:
    _, listed = wired.get("/api/v1/financial/orders")
    order_id = listed["orders"][0]["internal_order_id"]

    status, body = wired.get(f"/api/v1/financial/orders/{order_id}")
    assert status == 200
    # The venue's identifier survives the restart-shaped read path (§23).
    assert body["order"]["broker_order_id"] == "broker-42"
    assert [t["to_status"] for t in body["transitions"]] == [
        "PENDING_NEW",
        "ACCEPTED",
        "PARTIALLY_FILLED",
    ]
    assert body["order"]["filled_quantity"] == pytest.approx(1.0)
    assert body["order"]["status"] == "PARTIALLY_FILLED"
    assert body["fills"][0]["quantity"] == pytest.approx(1.0)


def test_unknown_order_is_404_not_an_empty_object(wired: KernelApi) -> None:
    status, body = wired.get("/api/v1/financial/orders/does-not-exist")
    assert status == 404
    assert "error" in body


def test_cash_reports_settled_reserved_and_available(wired: KernelApi) -> None:
    wired.store.post_cash(
        [
            CashPosting(
                transaction_id="funding", account_id="acct-1", amount_minor=500_000
            ),
            CashPosting(
                transaction_id="funding", account_id="counterparty", amount_minor=-500_000
            ),
        ]
    )
    status, body = wired.get("/api/v1/financial/cash")
    assert status == 200
    row = next(r for r in body["cash"] if r["account_id"] == "acct-1")
    assert row["settled_minor"] == 500_000
    assert row["reserved_minor"] == 0
    assert row["available_minor"] == 500_000


def test_invariant_endpoint_actually_runs_the_suite(wired: KernelApi) -> None:
    status, body = wired.get("/api/v1/financial/invariants")
    assert status == 200
    assert body["ok"] is True, body["failures"]
    assert body["checked"] > 0
    assert body["failures"] == []


def test_health_reports_backend_schema_and_safety(wired: KernelApi) -> None:
    status, body = wired.get("/api/v1/financial/health")
    assert status == 200
    assert body["backend"] == "sqlite"
    assert body["reachable"] is True
    assert body["schema"]["up_to_date"] is True
    assert body["safety"]["known"] is True
    assert body["safety"]["active_count"] == 0


def test_outbox_endpoint_surfaces_backlog_and_dead_letters(wired: KernelApi) -> None:
    status, body = wired.get("/api/v1/financial/outbox")
    assert status == 200
    assert body["available"] is True
    # order_requested + order_accepted + execution_completed, none published yet.
    assert body["backlog"] == 3
    assert len(body["pending"]) == 3
    assert body["dead_letters"] == []


def test_reconciliation_endpoint_reports_no_pass_yet(wired: KernelApi) -> None:
    status, body = wired.get("/api/v1/financial/reconciliation")
    assert status == 200
    assert body["last_run"] is None
    assert body["open_findings"] == []
    assert body["lockouts"]["active_count"] == 0


# ------------------------------------------------- unwired kernel must be honest


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/financial/ibor",
        "/api/v1/financial/positions",
        "/api/v1/financial/cash",
        "/api/v1/financial/orders",
        "/api/v1/financial/fills",
        "/api/v1/financial/invariants",
        "/api/v1/financial/health",
        "/api/v1/financial/outbox",
        "/api/v1/financial/reconciliation",
    ],
)
def test_unwired_kernel_is_reported_as_unavailable(unwired: KernelApi, path: str) -> None:
    status, body = unwired.get(path)
    assert status == 200
    assert body["available"] is False, f"{path} fabricated data: {body}"
    assert "reason" in body


# ------------------------------------------------------- lockout release RBAC


def _engage(kernel: KernelApi) -> str:
    lockout = kernel.store.engage_lockout(
        SafetyLockout(
            scope=LockoutScope.ACCOUNT,
            subject="acct-1",
            reason="CRITICAL cash mismatch vs broker",
            engaged_by="c5-reconciliation",
        )
    )
    return lockout.lockout_id


def test_authenticated_risk_admin_can_release(wired: KernelApi) -> None:
    lockout_id = _engage(wired)
    status, body = wired.release(lockout_id, RISK_ADMIN_TOKEN)
    assert status == 200, body
    assert body["released_by"] == "risk-1"
    assert body["active"] is False
    assert wired.store.active_lockouts() == []


def test_viewer_cannot_release_even_though_authenticated(wired: KernelApi) -> None:
    lockout_id = _engage(wired)
    status, body = wired.release(lockout_id, VIEWER_TOKEN)
    assert status == 403, body
    assert "may not release" in body["error"]
    # The restriction must survive a refused release.
    assert len(wired.store.active_lockouts()) == 1


def test_operator_role_cannot_release_a_lockout(wired: KernelApi) -> None:
    """OPERATOR runs the desk; it does not clear a risk restriction."""
    lockout_id = _engage(wired)
    status, _ = wired.release(lockout_id, OPERATOR_TOKEN)
    assert status == 403
    assert len(wired.store.active_lockouts()) == 1


def test_unauthenticated_release_is_401(wired: KernelApi) -> None:
    lockout_id = _engage(wired)
    status, _ = wired.release(lockout_id, None)
    assert status == 401
    assert len(wired.store.active_lockouts()) == 1


def test_body_cannot_forge_operator_identity_or_role(wired: KernelApi) -> None:
    """A VIEWER token plus a perfect body is still a refusal."""
    lockout_id = _engage(wired)
    status, body = _request(
        "POST",
        f"http://127.0.0.1:{wired.port}/api/v1/financial/lockouts/"
        f"{lockout_id}/release",
        VIEWER_TOKEN,
        {"note": "ok", "operator_id": "risk-1", "role": "RISK_ADMIN"},
    )
    assert status == 403, body
    assert len(wired.store.active_lockouts()) == 1


def test_release_is_audited_with_the_server_resolved_actor(wired: KernelApi) -> None:
    lockout_id = _engage(wired)
    status, _ = wired.release(lockout_id, RISK_ADMIN_TOKEN)
    assert status == 200

    release_events = list(wired.audit.iter_event_payloads("SAFETY_LOCKOUT_RELEASED"))
    assert len(release_events) == 1
    assert release_events[0]["operator_id"] == "risk-1"
    assert release_events[0]["role"] == "RISK_ADMIN"
    assert release_events[0]["lockout_id"] == lockout_id

    # Engaged straight on the store, so the plane recorded no engagement.
    assert list(wired.audit.iter_event_payloads("SAFETY_LOCKOUT_ENGAGED")) == []


def test_release_is_idempotent_and_cannot_resurrect_a_lockout(wired: KernelApi) -> None:
    """A second release neither errors nor re-restricts: it stays released."""
    lockout_id = _engage(wired)
    assert wired.release(lockout_id, RISK_ADMIN_TOKEN)[0] == 200
    second_status, second_body = wired.release(lockout_id, RISK_ADMIN_TOKEN)
    assert second_status == 200, second_body
    assert second_body["active"] is False
    assert wired.store.active_lockouts() == []


def test_release_of_unknown_lockout_is_400(wired: KernelApi) -> None:
    status, body = wired.release("no-such-lockout", RISK_ADMIN_TOKEN)
    assert status == 400, body
    assert "unknown lockout" in body["error"]
