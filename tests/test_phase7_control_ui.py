"""Phase 7 tests: control plane RBAC + actions, views, metrics, HTTP roundtrip."""

import asyncio
import json
import urllib.request
from pathlib import Path

import pytest

from core.config import Settings
from core.control_plane import ControlAction, ControlPlane, OperatorRole
from core.event_bus import InMemoryEventBus
from core.persistence import SqliteMemoryStore
from core.risk_governor import RiskGovernor


@pytest.fixture()
def wired(tmp_path: Path):
    from communities.c4_strategy.strategy_agent import StrategyAgent
    from communities.c5_execution.adapters import PaperExecutionAdapter
    from communities.c5_execution.execution import OrderManager
    from core.risk_firewall import RiskConfig, RiskFirewall
    from simulation.paper_engine import PaperEngine

    store = SqliteMemoryStore(tmp_path / "cp.db")
    bus = InMemoryEventBus()
    engine = PaperEngine(bus, initial_balance=100000.0)
    adapter = PaperExecutionAdapter(engine)
    manager = OrderManager(
        event_bus=bus,
        adapter=adapter,
        quantity_provider=lambda p: (
            100000.0 * p.final_position_size_pct / 100.0 / max(p.strategy.entry_price, 1e-9)
        ),
    )
    agent = StrategyAgent(bus, RiskFirewall(RiskConfig()))
    governor = RiskGovernor(bus)
    plane = ControlPlane(
        store=store,
        event_bus=bus,
        risk_governor=governor,
        strategy_agent=agent,
        order_manager=manager,
        paper_engine=engine,
        price_lookup=lambda s: 99.0,
        flatten_callback=lambda eid, price: _noop_flatten(engine, eid, price),
        positions_view=lambda: {
            eid: {"symbol": p.receipt.symbol, "action": p.action}
            for eid, p in engine.open_positions.items()
        },
    )
    return plane, store, engine, manager, agent, governor


async def _noop_flatten(engine, execution_id: str, price: float) -> None:
    engine.settle_position(execution_id, price)


# ---------------------------------------------------------------------- RBAC


def test_rbac_matrix_enforced(wired) -> None:
    plane = wired[0]
    assert plane.authorize(OperatorRole.VIEWER, ControlAction.PAUSE_TRADING) is False
    assert plane.authorize(OperatorRole.OPERATOR, ControlAction.PAUSE_TRADING) is True
    assert plane.authorize(OperatorRole.OPERATOR, ControlAction.RESET_LOCKOUT) is False
    assert plane.authorize(OperatorRole.RISK_ADMIN, ControlAction.RESET_LOCKOUT) is True
    assert plane.authorize(OperatorRole.ADMIN, ControlAction.APPROVE_LIVE_CAPITAL) is True
    assert plane.authorize(OperatorRole.RISK_ADMIN, ControlAction.APPROVE_LIVE_CAPITAL) is False


def test_execute_requires_identity_and_logs_denials(wired) -> None:
    plane, store, *_ = wired

    async def _run():
        with pytest.raises(ValueError):
            await plane.execute("  ", "OPERATOR", "pause_trading")
        with pytest.raises(PermissionError, match="unknown role"):
            await plane.execute("op-1", "SUPERUSER", "pause_trading")
        with pytest.raises(PermissionError, match="may not perform"):
            await plane.execute("op-1", "VIEWER", "pause_trading")
        result = await plane.execute("op-2", "OPERATOR", "pause_trading")
        return result

    result = asyncio.run(_run())
    assert result["authorized"] is True and result["result"]["paused"] is True
    denials = [p for p in store.iter_event_payloads("CONTROL_ACTION") if not p["authorized"]]
    approvals = [p for p in store.iter_event_payloads("CONTROL_ACTION") if p["authorized"]]
    assert len(denials) == 2 and len(approvals) == 1


def test_freeze_unfreeze_and_cancel_actions(wired) -> None:
    plane, store, engine, manager, agent, _governor = wired

    async def _run():
        await plane.execute("op-3", "OPERATOR", "freeze_symbol", {"symbol": "BTC/USD"})
        frozen = "BTC/USD" in agent._frozen_symbols
        await plane.execute("op-3", "OPERATOR", "unfreeze_symbol", {"symbol": "BTC/USD"})
        unfrozen = "BTC/USD" not in agent._frozen_symbols

        # Seed a live (non-terminal) order to cancel
        from schemas.contracts import OrderRequest

        manager.orders["c1"] = OrderRequest(
            client_order_id="c1",
            strategy_id="s1",
            symbol="BTC/USD",
            side="BUY",
            quantity=1.0,
        )
        cancel_result = await plane.execute("op-4", "OPERATOR", "cancel_open_orders")
        return frozen, unfrozen, cancel_result

    frozen, unfrozen, cancel_result = asyncio.run(_run())
    assert frozen is True and unfrozen is True
    assert cancel_result["result"]["cancelled"] == ["c1"]


def test_kill_switch_action_and_admin_only_reset(wired) -> None:
    plane, store, engine, manager, agent, governor = wired

    async def _seed_and_trigger():
        receipt = await manager.on_plan(_plan_for_kill(), locked_out=False)
        assert receipt is not None
        return await plane.execute("risk-op", "RISK_ADMIN", "trigger_kill_switch")

    def _plan_for_kill():
        from schemas.contracts import PortfolioAllocationPlan, StrategySpecification

        spec = StrategySpecification(
            hypothesis_id="h",
            symbol="BTC/USD",
            action="BUY",
            entry_price=100.0,
            stop_loss_price=97.0,
            take_profit_price=106.0,
            position_size_pct=10.0,
        )
        return PortfolioAllocationPlan(
            strategy=spec,
            approved=True,
            final_position_size_pct=10.0,
            portfolio_status="HEALTHY",
            drawdown_pct=0.0,
        )

    result = asyncio.run(_seed_and_trigger())
    assert result["result"]["flattened"] == 1
    assert governor.locked_out is True

    async def _viewer_try_reset():
        await plane.execute("viewer-1", "VIEWER", "reset_lockout")

    with pytest.raises(PermissionError):
        asyncio.run(_viewer_try_reset())

    reset = asyncio.run(plane.execute("admin-9", "RISK_ADMIN", "reset_lockout"))
    assert reset["result"]["new_state"] == "NORMAL"


def test_approve_live_capital_is_admin_only_and_audited(wired) -> None:
    plane, store, *_ = wired

    async def _run():
        with pytest.raises(PermissionError):
            await plane.execute("op-x", "OPERATOR", "approve_live_capital")
        return await plane.execute("chief-1", "ADMIN", "approve_live_capital", {"note": "board"})

    result = asyncio.run(_run())
    assert result["result"]["live_capital_approved_by"] == "chief-1"
    approvals = store.iter_event_payloads("LIVE_CAPITAL_APPROVAL")
    assert len(approvals) == 1 and approvals[0]["operator_id"] == "chief-1"


# --------------------------------------------------------------- views/server


def test_views_shapes_and_metrics(tmp_path: Path) -> None:
    from api.views import prometheus_metrics
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=40)
    from core.config import Settings
    _settings = Settings(model_provider="none", autonomy_mode="AUTONOMOUS")
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "views.db",
        settings=_settings,
    )
    asyncio.run(runner.run())
    builder = runner.build_snapshot_builder()

    exec_view = builder.executive()
    for key in ("cash_balance", "cumulative_realized_pnl", "chain_valid", "emergency_state"):
        assert key in exec_view
    assert exec_view["chain_valid"] is True

    executions = builder.executions(limit=5)
    assert executions, "closed trades expected"
    drill = builder.decision_drilldown(executions[0]["execution_id"])
    assert drill["chain_complete"] is True
    for section in ("decision", "reason", "evidence", "verification", "risk", "outcome"):
        assert section in drill

    health = builder.health()
    assert health["audit_chain_valid"] is True

    accounting = builder.accounting()
    assert accounting["balanced"] is True

    metrics = prometheus_metrics(exec_view)
    assert "# TYPE aios_cash_balance gauge" in metrics
    assert 'aios_emergency_state{state="' in metrics


def test_http_server_requires_bearer_token_when_configured(tmp_path: Path) -> None:
    from api.server import CommandCenterServer
    from api.views import SystemSnapshotBuilder

    store = SqliteMemoryStore(tmp_path / "auth.db")
    server = CommandCenterServer(SystemSnapshotBuilder(store), port=0, auth_token="test-token")
    server.start()
    try:
        base = f"http://127.0.0.1:{server.port}"
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"{base}/api/v1/executive", timeout=5)
        assert error.value.code == 401
        request = urllib.request.Request(
            f"{base}/api/v1/executive",
            headers={"Authorization": "Bearer test-token", "X-Request-ID": "req-123"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.headers["X-Request-ID"] == "req-123"
            assert json.loads(response.read())["chain_valid"] is True
        with urllib.request.urlopen(f"{base}/api/v1/health", timeout=5) as response:
            assert response.status == 200
    finally:
        server.stop()


def test_http_server_roundtrip(tmp_path: Path) -> None:
    from api.server import CommandCenterServer
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=40)
    runner = ReplayRunner(
        csv_path_by_symbol={"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"},
        store_path=tmp_path / "http.db",
        settings=Settings(model_provider="none", autonomy_mode="AUTONOMOUS"),
    )
    asyncio.run(runner.run())
    plane = runner.build_control_plane()
    server = CommandCenterServer(runner.build_snapshot_builder(), plane, port=0)
    server.start()
    try:
        base = f"http://127.0.0.1:{server.port}"

        with urllib.request.urlopen(f"{base}/api/v1/executive", timeout=5) as resp:
            body = json.loads(resp.read())
        assert body["chain_valid"] is True

        with urllib.request.urlopen(f"{base}/metrics", timeout=5) as resp:
            text = resp.read().decode()
        assert "aios_events_logged" in text

        with urllib.request.urlopen(base + "/", timeout=5) as resp:
            html = resp.read().decode()
        assert "COMMAND CENTER" in html.upper().replace("&#8209;", "-")

        # RBAC denial over HTTP -> 403
        req = urllib.request.Request(
            f"{base}/api/v1/control/reset_lockout",
            data=json.dumps({"operator_id": "x", "role": "VIEWER"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            raised = False
        except urllib.error.HTTPError as err:
            # Authentication is intentionally disabled for this read-only
            # fixture; unauthenticated mutation is rejected before RBAC.
            raised = err.code == 401
        assert raised, "Unauthenticated reset must be rejected"
    finally:
        server.stop()
