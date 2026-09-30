"""Phase 5 tests: order lifecycle, kill switch, emergency machine, ACL, shadow."""

import asyncio
from pathlib import Path

import pytest

from communities.c5_execution.adapters import (
    CcxtExecutionAdapter,
    ExecutionUnavailableError,
    PaperExecutionAdapter,
)
from communities.c5_execution.broker_reconciliation import snapshot_from_rows
from communities.c5_execution.execution import KillSwitch, OrderManager
from communities.c5_execution.oms import DurableOrderManager, OrderBlocked
from communities.c5_execution.reconciliation import ReconciliationEngine
from core.event_bus import EventTopic, InMemoryEventBus
from core.financial_kernel import (
    AnomalyKind,
    CashPosting,
    Fill,
    ReconciliationMode,
    SqliteFinancialStore,
)
from core.persistence import SqliteMemoryStore
from core.risk_governor import RiskGovernor, load_lockout_from_store
from core.safety_plane import SafetyPlane
from core.security import ACLBus, AgentPrincipal
from schemas.contracts import (
    EmergencyStateValue,
    OrderSide,
    PortfolioAllocationPlan,
    StrategySpecification,
)


def _plan(size: float = 5.0, entry: float = 100.0) -> PortfolioAllocationPlan:
    spec = StrategySpecification(
        hypothesis_id="h1",
        symbol="BTC/USD",
        action="BUY",
        entry_price=entry,
        stop_loss_price=entry * 0.97,
        take_profit_price=entry * 1.06,
        position_size_pct=size,
    )
    return PortfolioAllocationPlan(
        strategy=spec,
        approved=True,
        final_position_size_pct=size,
        portfolio_status="HEALTHY",
        drawdown_pct=0.0,
    )


def _engine_and_manager(balance: float = 100000.0):
    from simulation.paper_engine import PaperEngine

    bus = InMemoryEventBus()
    engine = PaperEngine(bus, initial_balance=balance)
    adapter = PaperExecutionAdapter(engine)
    manager = OrderManager(
        event_bus=bus,
        adapter=adapter,
        quantity_provider=lambda plan: (
            balance * plan.final_position_size_pct / 100.0 / max(plan.strategy.entry_price, 1e-9)
        ),
    )
    return bus, engine, manager


def test_order_lifecycle_and_idempotency() -> None:
    async def _run():
        bus, engine, manager = _engine_and_manager()
        await bus.start()

        plan = _plan()  # ONE plan object = one idempotency identity
        receipt1 = await manager.on_plan(plan, locked_out=False)
        assert receipt1 is not None
        filled = [o for o in manager.orders.values() if o.status.value == "FILLED"]
        assert len(filled) == 1

        # Retrying the SAME plan is suppressed by the client_order_id key
        receipt2 = await manager.on_plan(plan, locked_out=False)
        assert receipt2 is None
        assert len(manager.orders) == 1

        # A genuinely different plan executes normally
        other = _plan(size=1.0)
        other_receipt = await manager.on_plan(other, locked_out=False)
        _ = other_receipt  # may fill or hit position cap; not the assertion target
        assert len(manager.orders) == 2

        await bus.stop()
        return engine

    engine = asyncio.run(_run())
    assert engine.cash_balance < 100000.0


def test_order_manager_blocks_when_locked_out() -> None:
    async def _run():
        bus, engine, manager = _engine_and_manager()
        await bus.start()
        receipt = await manager.on_plan(_plan(), locked_out=True)
        await bus.stop()
        return receipt, engine.cash_balance

    receipt, cash = asyncio.run(_run())
    assert receipt is None
    assert cash == 100000.0


# ------------------------------------------------------------------ kill switch


def test_kill_switch_flatten_lockout_and_human_reset(tmp_path: Path) -> None:
    from simulation.paper_engine import PaperEngine

    async def _run():
        bus = InMemoryEventBus()
        await bus.start()
        governor = RiskGovernor(bus)
        engine = PaperEngine(bus, initial_balance=100000.0)
        adapter = PaperExecutionAdapter(engine)
        manager = OrderManager(
            event_bus=bus,
            adapter=adapter,
            quantity_provider=lambda p: (
                100000.0 * p.final_position_size_pct / 100.0 / p.strategy.entry_price
            ),
        )

        await manager.on_plan(_plan(size=10.0), locked_out=False)
        assert len(engine.open_positions) == 1

        flattened_ids: list[str] = []

        async def flatten(eid: str, price: float) -> None:
            assert engine.settle_position(eid, price) is not None
            flattened_ids.append(eid)

        kill = KillSwitch(
            governor=governor,
            positions_view=lambda: {
                eid: {"symbol": p.receipt.symbol, "action": p.action}
                for eid, p in engine.open_positions.items()
            },
            flatten_callback=flatten,
            price_lookup=lambda s: 99.0,
        )
        count = await kill.trigger("test halt", triggered_by="test")
        await bus.stop()
        return governor, engine, count

    governor, engine, count = asyncio.run(_run())
    assert count == 1
    assert engine.open_positions == {}
    assert governor.locked_out is True
    assert governor.state == EmergencyStateValue.EMERGENCY_HALT

    # Empty operator identity refused; valid reset clears lockout
    async def _reset(op_id: str):
        return await governor.human_reset(op_id)

    with pytest.raises(ValueError):
        asyncio.run(_reset("   "))
    event = asyncio.run(governor.human_reset("operator-7", "reviewed incident"))
    assert event.new_state == EmergencyStateValue.NORMAL
    assert governor.locked_out is False


def test_lockout_persists_across_restart_until_human_reset(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "lock.db")
    bus = InMemoryEventBus()

    async def _engage() -> None:
        await bus.start()
        governor = RiskGovernor(bus)
        # Route through the bus so the store logger would capture it in prod;
        # here we append directly to keep the test focused on persistence.
        event = await governor.escalate(
            EmergencyStateValue.EMERGENCY_HALT, "crash", triggered_by="system"
        )
        store.append_event("aios.risk.emergency", None, event.model_dump(mode="json"))
        await bus.stop()

    asyncio.run(_engage())
    assert load_lockout_from_store(store) is True

    reset_event = {
        "new_state": "NORMAL",
        "triggered_by": "operator-1",
        "lockout_engaged": False,
    }
    store.append_event("aios.risk.emergency", None, reset_event)
    assert load_lockout_from_store(store) is False


def _positions_only_snapshot(positions: dict[str, float]):
    """What the paper venue can actually answer: positions, and nothing else."""
    return snapshot_from_rows(
        broker="paper",
        account_id="default",
        mode=ReconciliationMode.FULL_SNAPSHOT,
        positions=positions,
        adapter_version="paper-positions-only-1.0",
        covers_orders=False,
        covers_executions=False,
    )


def test_reconciliation_failure_engages_durable_lockout_and_escalates(tmp_path: Path) -> None:
    """§26: a venue/IBOR divergence restricts the account AND escalates.

    This replaces the retired per-bar `ReconciliationReport` path. The signal is
    no longer a boolean assembled from free-text mismatch strings; it is a
    CRITICAL finding persisted by the durable engine, which engages a
    safety-plane restriction through the same store the API and the operator
    surface read.
    """
    store = SqliteFinancialStore(tmp_path / "recon.db")
    try:
        safety = SafetyPlane(store, broker="paper")
        engine = ReconciliationEngine(store, account_id="default", safety=safety)

        # A clean pass over an empty book engages nothing.
        clean = engine.reconcile(_positions_only_snapshot({}))
        assert clean.requires_lockout is False
        assert clean.critical() == []
        assert safety.is_blocked(account_id="default", broker="paper").blocked is False

        # Now internal state holds a position the venue does not report.
        store.post_cash(
            [
                CashPosting(transaction_id="seed", account_id="default", amount_minor=100_000),
                CashPosting(transaction_id="seed", account_id="counterparty", amount_minor=-100_000),
            ]
        )
        oms = DurableOrderManager(store, account_id="default", safety=safety)
        order = oms.accept(
            oms.prepare_order(
                client_order_id="recon-order",
                strategy_id="s1",
                symbol="BTC/USD",
                side=OrderSide.BUY,
                quantity=5.0,
            ).internal_order_id
        )
        store.apply_fill(
            Fill(
                fill_id="f-recon",
                order_id=order.internal_order_id,
                broker_execution_id="exec-recon",
                symbol="BTC/USD",
                side=OrderSide.BUY,
                quantity=5.0,
                price=100.0,
            )
        )

        result = engine.reconcile(_positions_only_snapshot({}))
        assert result.requires_lockout is True
        assert [f.kind for f in result.critical()] == [AnomalyKind.POSITION_MISMATCH]
        # The restriction is durable and consultable before any venue call.
        assert safety.is_blocked(account_id="default", broker="paper").blocked is True
        with pytest.raises(OrderBlocked):
            oms.prepare_order(
                client_order_id="recon-order-2",
                strategy_id="s1",
                symbol="BTC/USD",
                side=OrderSide.BUY,
                quantity=1.0,
            )

        async def _escalate() -> tuple[bool, EmergencyStateValue]:
            bus = InMemoryEventBus()
            await bus.start()
            governor = RiskGovernor(bus)
            allowed_before = not governor.locked_out
            # Exactly what the composition root does with the durable verdict.
            if result.requires_lockout:
                await governor.escalate(
                    EmergencyStateValue.EXECUTION_FAILURE,
                    f"reconciliation run {result.run.run_id} raised "
                    f"{len(result.critical())} critical finding(s); scope "
                    f"{result.lockout_scope}",
                    triggered_by="reconciler",
                )
            await bus.stop()
            return allowed_before, governor.state

        allowed_before, state = asyncio.run(_escalate())
        assert allowed_before is True
        assert state == EmergencyStateValue.EXECUTION_FAILURE

        # Once the venue reports the position too, the book is consistent again
        # and a fresh pass raises nothing.
        consistent = engine.reconcile(_positions_only_snapshot({"BTC/USD": 5.0}))
        assert consistent.critical() == []
    finally:
        store.close()


def test_drawdown_halt_via_governor() -> None:
    async def _run():
        bus = InMemoryEventBus()
        await bus.start()
        governor = RiskGovernor(bus)
        allowed_normal = await governor.observe_drawdown(1.0, halt_threshold_pct=3.0)
        await governor.observe_drawdown(3.2, halt_threshold_pct=3.0)
        await bus.stop()
        return allowed_normal, governor.locked_out

    normal, locked = asyncio.run(_run())
    assert normal is True
    assert locked is True


# ------------------------------------------------------------------------ ACL


def test_acl_enforces_publish_and_subscribe_capabilities() -> None:
    inner = InMemoryEventBus()

    async def handler(payload: object) -> None:
        return None

    async def _run():
        bus = ACLBus(inner)
        await bus.start()
        bus.register(
            AgentPrincipal(
                agent_id="news-agent",
                publish_topics=frozenset({EventTopic.HYPOTHESIS_GENERATED}),
                subscribe_topics=frozenset({EventTopic.DATA_ACQUIRED}),
            )
        )

        # Allowed publish
        await bus.publish_as("unknown-agent", EventTopic.DATA_ACQUIRED, _plan()) if False else None

        from schemas.contracts import MarketDataPayload, PriceData

        payload = MarketDataPayload(
            symbol="X/USD",
            timeframe="1d",
            price_data=PriceData(open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0),
        )
        with pytest.raises(PermissionError):
            await bus.publish_as("ghost", EventTopic.DATA_ACQUIRED, payload)
        with pytest.raises(PermissionError):
            await bus.publish_as("news-agent", EventTopic.RISK_EMERGENCY, payload)
        await bus.publish_as("news-agent", EventTopic.HYPOTHESIS_GENERATED, payload)  # ok

        with pytest.raises(PermissionError):
            await bus.subscribe_as("news-agent", EventTopic.RISK_EMERGENCY, handler)
        await bus.subscribe_as("news-agent", EventTopic.DATA_ACQUIRED, handler)  # ok

        # System-level API bypasses agent ACLs by design (composition root only)
        await bus.publish(EventTopic.RISK_EMERGENCY, payload)
        await bus.stop()

    asyncio.run(_run())


# --------------------------------------------------------------------- shadow


def test_shadow_mode_never_mutates_cash() -> None:
    from simulation.paper_engine import PaperEngine

    async def _run():
        bus = InMemoryEventBus()
        await bus.start()
        shadow = PaperEngine(bus, initial_balance=100000.0, shadow_mode=True)
        adapter = PaperExecutionAdapter(shadow)
        manager = OrderManager(
            event_bus=bus,
            adapter=adapter,
            quantity_provider=lambda p: (
                100000.0 * p.final_position_size_pct / 100.0 / max(p.strategy.entry_price, 1e-9)
            ),
        )
        receipt = await manager.on_plan(_plan(size=25.0), locked_out=False)
        await bus.stop()
        return shadow, receipt

    engine, receipt = asyncio.run(_run())
    assert receipt is not None
    assert receipt.venue == "shadow"
    assert len(engine.open_positions) == 1  # tracked...
    assert engine.cash_balance == 100000.0  # ...but zero cash movement


# ------------------------------------------------------- ccxt adapter honesty


def test_ccxt_execution_adapter_refuses_without_explicit_optin() -> None:
    with pytest.raises(ExecutionUnavailableError, match="AIOS_ALLOW_LIVE_EXECUTION"):
        CcxtExecutionAdapter("binance", api_key_env="K", secret_env="S", env={})

    with pytest.raises(ExecutionUnavailableError, match="credentials"):
        CcxtExecutionAdapter(
            "binance",
            api_key_env="K",
            secret_env="S",
            env={"AIOS_ALLOW_LIVE_EXECUTION": "1"},
        )


def test_ccxt_execution_adapter_caps_notional_when_fully_enabled() -> None:
    adapter = CcxtExecutionAdapter(
        "binance",
        api_key_env="AIOS_TEST_KEY",
        secret_env="AIOS_TEST_SECRET",
        env={
            "AIOS_ALLOW_LIVE_EXECUTION": "1",
            "AIOS_EXCHANGE_TESTNET": "1",
            "AIOS_TEST_KEY": "k",
            "AIOS_TEST_SECRET": "s",
        },
    )
    assert adapter.testnet is True
    big_plan = _plan(size=50.0, entry=100000.0)
    with pytest.raises(ExecutionUnavailableError, match="micro-live cap"):
        asyncio.run(adapter.submit(big_plan, quantity=10.0))
