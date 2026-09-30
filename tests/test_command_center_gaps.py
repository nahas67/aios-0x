"""Command-center backend gaps (plan §4, lanes A2/A3/A4/A6 + B2/B3).

TDD red step: every test here fails until the lane implementation lands in
``api/server.py``, ``api/views.py`` and ``core/control_plane.py``.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.server import CommandCenterServer
from api.views import SystemSnapshotBuilder
from communities.c5_execution.reconciliation import ReconciliationEngine
from communities.c10_world.regime_engine import RegimeEngine
from core.control_plane import ControlPlane
from core.event_bus import InMemoryEventBus
from core.financial_kernel import (
    AnomalyKind,
    FindingStatus,
    LockoutScope,
    ReconciliationFinding,
    ReconciliationRun,
    ReconciliationSeverity,
    SqliteFinancialStore,
)
from core.persistence import SqliteMemoryStore
from core.risk_governor import RiskGovernor
from kernel.bootstrap import create_kernel
from kernel.registries import ModelRegistry
from schemas.contracts import MarketDataPayload, PriceData

LIMIT_ENDPOINTS = [
    "/api/v1/financial/orders",
    "/api/v1/financial/fills",
    "/api/v1/financial/outbox",
    "/api/v1/financial/reconciliation",
    "/api/v1/audit",
    "/api/v1/platform-events",
    "/api/v1/evaluations",
]


def _get(port: int, path: str) -> tuple[int, dict[str, Any]]:
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            return exc.code, {}


@pytest.fixture(scope="module")
def server_port(tmp_path_factory: pytest.TempPathFactory) -> Any:
    store = SqliteMemoryStore(tmp_path_factory.mktemp("gaps") / "audit.db")
    store.append_event("SEED", None, {"n": 1})
    builder = SystemSnapshotBuilder(store=store)
    server = CommandCenterServer(builder, None, port=0)
    server.start()
    time.sleep(0.3)
    yield server.port
    server.stop()
    store.close()


def _plane(store: SqliteMemoryStore, engine: Any = None) -> ControlPlane:
    kwargs: dict[str, Any] = {}
    if engine is not None:
        kwargs["reconciliation_engine"] = engine
    return ControlPlane(
        store=store,
        event_bus=InMemoryEventBus(),
        risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
        strategy_agent=None,
        order_manager=None,
        **kwargs,
    )


def _seed_finding(fin: SqliteFinancialStore) -> str:
    run = ReconciliationRun(account_id="acct-1", broker="paper")
    finding = ReconciliationFinding(
        run_id=run.run_id,
        kind=AnomalyKind.STALE_STATUS,
        severity=ReconciliationSeverity.WARNING,
        subject="BTC/USD",
        detail="status drift on test finding",
        scope=LockoutScope.NONE,
    )
    fin.record_reconciliation(run, [finding])
    return finding.finding_id


# ------------------------------------------------------------------ A2


def test_event_backbone_routed(server_port: int) -> None:
    status, payload = _get(server_port, "/api/v1/event-backbone")
    assert status == 200
    assert payload["wired"] is False
    assert payload["consumer_lag"] is None


def test_event_backbone_wired_bus(tmp_path: Path) -> None:
    class _Bus:
        def health(self) -> dict[str, Any]:
            return {"reachable": True, "backend": "test"}

    builder = SystemSnapshotBuilder(
        store=SqliteMemoryStore(tmp_path / "a.db"),
        event_bus=_Bus(),  # type: ignore[arg-type]
    )
    payload = builder.event_backbone_view()
    assert payload["wired"] is True
    assert payload["reachable"] is True


# ------------------------------------------------------------------ B3


@pytest.mark.parametrize("path", LIMIT_ENDPOINTS)
def test_limit_invalid_returns_400(server_port: int, path: str) -> None:
    status, payload = _get(server_port, f"{path}?limit=abc")
    assert status == 400, (path, status, payload)
    assert "error" in payload


@pytest.mark.parametrize("path", LIMIT_ENDPOINTS)
def test_limit_negative_clamps_to_default(server_port: int, path: str) -> None:
    status, _ = _get(server_port, f"{path}?limit=-1")
    assert status == 200, (path, status)


def test_limit_valid_still_applies(server_port: int) -> None:
    status, payload = _get(server_port, "/api/v1/platform-events?limit=3")
    assert status == 200
    assert len(payload["events"]) <= 3


# ------------------------------------------------------------------ B2


def test_resolve_finding_end_to_end_via_engine(tmp_path: Path) -> None:
    fin = SqliteFinancialStore(tmp_path / "fin.db")
    finding_id = _seed_finding(fin)
    engine = ReconciliationEngine(store=fin, account_id="acct-1")
    store = SqliteMemoryStore(tmp_path / "audit.db")
    plane = _plane(store, engine)

    record = asyncio.run(
        plane.execute(
            "admin-1",
            "ADMIN",
            "resolve_reconciliation_finding",
            {"finding_id": finding_id, "note": "verified against broker statement"},
        )
    )
    assert record["authorized"] is True
    assert record["result"]["finding_id"] == finding_id
    assert record["result"]["resolved"] is True
    assert fin.findings_by_id(finding_id).status is FindingStatus.RESOLVED


def test_resolve_finding_operator_allowed_non_critical(tmp_path: Path) -> None:
    fin = SqliteFinancialStore(tmp_path / "fin.db")
    finding_id = _seed_finding(fin)
    engine = ReconciliationEngine(store=fin, account_id="acct-1")
    plane = _plane(SqliteMemoryStore(tmp_path / "audit.db"), engine)
    record = asyncio.run(
        plane.execute(
            "op-1", "OPERATOR", "resolve_reconciliation_finding", {"finding_id": finding_id}
        )
    )
    assert record["result"]["resolved"] is True


def test_resolve_finding_unknown_id_is_value_error(tmp_path: Path) -> None:
    fin = SqliteFinancialStore(tmp_path / "fin.db")
    engine = ReconciliationEngine(store=fin, account_id="acct-1")
    plane = _plane(SqliteMemoryStore(tmp_path / "audit.db"), engine)
    with pytest.raises(ValueError, match="unknown finding"):
        asyncio.run(
            plane.execute(
                "admin-1", "ADMIN", "resolve_reconciliation_finding", {"finding_id": "nope"}
            )
        )


def test_resolve_finding_audit_fallback_without_engine(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "audit.db")
    plane = _plane(store)
    record = asyncio.run(
        plane.execute(
            "op-1",
            "OPERATOR",
            "resolve_reconciliation_finding",
            {"finding_id": "f-123", "note": "no engine wired"},
        )
    )
    assert record["result"] == {
        "finding_id": "f-123",
        "resolved": True,
        "note": "no engine wired",
        "via": "audit-record",
    }
    kinds = [p for p in store.iter_event_payloads("RECONCILIATION_FINDING_RESOLVED")]
    assert kinds and kinds[0]["finding_id"] == "f-123"


def test_resolve_finding_viewer_denied(tmp_path: Path) -> None:
    plane = _plane(SqliteMemoryStore(tmp_path / "audit.db"))
    with pytest.raises(PermissionError):
        asyncio.run(
            plane.execute("v-1", "VIEWER", "resolve_reconciliation_finding", {"finding_id": "f-1"})
        )


# ------------------------------------------------------------------ A3


def test_audit_verify_tmp_store(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "a.db")
    for i in range(5):
        store.append_event("K", None, {"i": i})
    payload = SystemSnapshotBuilder(store=store).audit_verify()
    assert payload["valid"] is True
    assert payload["blocks_checked"] == 5
    assert payload["breaks"] == []
    tail = store._conn.execute("SELECT hash FROM event_log ORDER BY seq DESC LIMIT 1").fetchone()
    assert payload["head_hash"] == tail["hash"]
    store.close()


def test_audit_verify_shipped_db(tmp_path: Path) -> None:
    shipped = Path("data/aios.db")
    assert shipped.exists(), "shipped data/aios.db required for this honesty check"
    copy = tmp_path / "aios-copy.db"
    shutil.copy(shipped, copy)  # never touch the shipped file itself
    store = SqliteMemoryStore(copy)
    payload = SystemSnapshotBuilder(store=store).audit_verify()
    raw = sqlite3.connect(str(copy))
    count = raw.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]
    tail = raw.execute("SELECT hash FROM event_log ORDER BY seq DESC LIMIT 1").fetchone()[0]
    raw.close()
    assert count > 1000
    assert payload["valid"] is True
    assert payload["blocks_checked"] == count
    assert payload["head_hash"] == tail
    assert payload["breaks"] == []
    store.close()


def test_audit_verify_routed(server_port: int) -> None:
    status, payload = _get(server_port, "/api/v1/audit/verify")
    assert status == 200
    assert payload["valid"] is True
    assert payload["blocks_checked"] >= 1
    assert payload["breaks"] == []
    assert isinstance(payload["head_hash"], str) and len(payload["head_hash"]) == 64


# ------------------------------------------------------------------ A4


def test_models_registry_present(tmp_path: Path) -> None:
    kernel = create_kernel()
    registry = ModelRegistry(kernel.provenance, kernel.promotions)
    registry.register(
        model_id="trend-v1",
        version="v3",
        model_type="logreg",
        feature_ref={"feature_id": "f", "version": "v1"},
    )
    bridge = SimpleNamespace(kernel=SimpleNamespace(models=registry))
    builder = SystemSnapshotBuilder(store=SqliteMemoryStore(tmp_path / "a.db"))
    builder.kernel_bridge = bridge
    payload = builder.models_registry_view()
    assert payload["available"] is True
    assert len(payload["models"]) == 1
    row = payload["models"][0]
    assert row["id"] == "trend-v1@v3"
    assert row["name"] == "trend-v1"
    assert row["version"] == "v3"
    assert row["status"] == "DEFINED"


def test_models_registry_absent(tmp_path: Path) -> None:
    builder = SystemSnapshotBuilder(store=SqliteMemoryStore(tmp_path / "a.db"))
    assert builder.models_registry_view() == {"available": False, "models": []}


def test_models_registry_routed(server_port: int) -> None:
    status, payload = _get(server_port, "/api/v1/models/registry")
    assert status == 200
    assert payload == {"available": False, "models": []}


# ------------------------------------------------------------------ A6


def _feed(engine: RegimeEngine, symbol: str) -> None:
    async def _go() -> None:
        for i in range(6):
            px = 100.0 + i
            await engine.on_data_acquired(
                MarketDataPayload(
                    symbol=symbol,
                    timeframe="1d",
                    price_data=PriceData(
                        open=px, high=px + 1.0, low=px - 1.0, close=px, volume=10.0
                    ),
                    is_simulated=True,
                )
            )

    asyncio.run(_go())


def test_instruments_from_regimes(tmp_path: Path) -> None:
    engine = RegimeEngine(event_bus=InMemoryEventBus())
    _feed(engine, "BTC/USD")
    _feed(engine, "ETH/USD")
    builder = SystemSnapshotBuilder(
        store=SqliteMemoryStore(tmp_path / "a.db"), regime_engine=engine
    )
    payload = builder.instruments_view()
    symbols = {row["symbol"] for row in payload["instruments"]}
    assert {"BTC/USD", "ETH/USD"} <= symbols
    for row in payload["instruments"]:
        assert set(row) >= {"symbol", "name", "category"}


def test_instruments_empty_without_sources(tmp_path: Path) -> None:
    builder = SystemSnapshotBuilder(store=SqliteMemoryStore(tmp_path / "a.db"))
    assert builder.instruments_view() == {"instruments": []}


def test_instruments_routed(server_port: int) -> None:
    status, payload = _get(server_port, "/api/v1/market/instruments")
    assert status == 200
    assert isinstance(payload["instruments"], list)
