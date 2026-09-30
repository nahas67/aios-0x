"""Autonomy modes, SUPERVISED approval queue, settings view masking."""

import asyncio
from pathlib import Path

import pytest

from core.control_plane import AutonomyMode, ControlAction, ControlPlane
from core.event_bus import InMemoryEventBus
from core.persistence import SqliteMemoryStore
from core.risk_governor import RiskGovernor
from schemas.contracts import PortfolioAllocationPlan, StrategySpecification


def _plan(symbol: str = "BTC/USD") -> PortfolioAllocationPlan:
    spec = StrategySpecification(
        hypothesis_id="h",
        symbol=symbol,
        action="BUY",
        entry_price=100.0,
        stop_loss_price=97.0,
        take_profit_price=106.0,
        position_size_pct=5.0,
    )
    return PortfolioAllocationPlan(
        strategy=spec,
        approved=True,
        final_position_size_pct=5.0,
        portfolio_status="HEALTHY",
        drawdown_pct=0.0,
    )


@pytest.fixture()
def plane(tmp_path: Path):
    store = SqliteMemoryStore(tmp_path / "auto.db")
    bus = InMemoryEventBus()
    return (
        ControlPlane(
            store=store,
            event_bus=bus,
            risk_governor=RiskGovernor(bus),
            strategy_agent=None,
            order_manager=None,
        ),
        store,
        bus,
    )


def test_autonomy_routing_modes(plane) -> None:
    cp, _store, _bus = plane
    plan = _plan()

    cp.autonomy = AutonomyMode.AUTONOMOUS
    assert cp.classify_plan(plan) == "EXECUTE"

    cp.autonomy = AutonomyMode.SUPERVISED
    assert cp.classify_plan(plan) == "QUEUE"

    cp.autonomy = AutonomyMode.ASSISTED
    assert cp.classify_plan(plan) == "HOLD"

    cp.autonomy = AutonomyMode.MANUAL
    assert cp.classify_plan(plan) == "HOLD"

    # pause overrides even AUTONOMOUS
    cp.autonomy = AutonomyMode.AUTONOMOUS
    cp.paused = True
    assert cp.classify_plan(plan) == "HOLD"


def test_supervised_queue_then_human_approve_executes(plane) -> None:
    cp, store, _bus = plane
    executed: list[str] = []

    async def bridge(plan):
        executed.append(plan.plan_id)
        return None  # receipt not needed for this assertion

    cp._execute_bridge(bridge)

    plan = _plan()

    async def _flow():
        await cp.queue_for_approval(plan)
        assert plan.plan_id in cp.pending_approvals
        # viewer cannot approve
        with pytest.raises(PermissionError):
            await cp.execute("v1", "VIEWER", "approve_plan", {"plan_id": plan.plan_id})
        result = await cp.execute("risk-1", "RISK_ADMIN", "approve_plan", {"plan_id": plan.plan_id})
        return result

    result = asyncio.run(_flow())
    assert result["result"]["approved"] is True
    assert executed == [plan.plan_id]
    assert cp.pending_approvals == {}

    decisions = store.iter_event_payloads("APPROVAL_DECISION")
    assert decisions[-1]["by"] == "risk-1"


def test_reject_plan_discards_without_execution(plane) -> None:
    cp, store, _bus = plane
    executed: list[str] = []
    cp._execute_bridge(lambda plan: executed.append(plan.plan_id) or asyncio.sleep(0))

    plan = _plan()

    async def _flow():
        await cp.queue_for_approval(plan)
        return await cp.execute(
            "risk-2", "RISK_ADMIN", "reject_plan", {"plan_id": plan.plan_id, "note": "bad"}
        )

    asyncio.run(_flow())
    assert executed == []
    assert plan.plan_id not in cp.pending_approvals


def test_set_autonomy_action_audited(plane) -> None:
    cp, store, _bus = plane

    async def _run():
        with pytest.raises(ValueError, match="unknown autonomy"):
            await cp.execute("op", "RISK_ADMIN", "set_autonomy", {"mode": "CHAOS"})
        return await cp.execute("op", "RISK_ADMIN", "set_autonomy", {"mode": "supervised"})

    result = asyncio.run(_run())
    assert result["result"]["autonomy"] == "SUPERVISED"
    actions = [p["action"] for p in store.iter_event_payloads("CONTROL_ACTION") if p["authorized"]]
    assert ControlAction.SET_AUTONOMY.value in actions


def test_settings_view_masks_secrets_and_reports_state(tmp_path: Path) -> None:
    from api.views import SystemSnapshotBuilder
    from core.config import Settings

    store = SqliteMemoryStore(tmp_path / "sv.db")
    bus = InMemoryEventBus()
    cp = ControlPlane(
        store=store,
        event_bus=bus,
        risk_governor=RiskGovernor(bus),
        strategy_agent=None,
        order_manager=None,
    )
    s = Settings(
        model_provider="openai_compatible",
        openai_api_key="provider-test-key",
        research_mode="auto",
        finnhub_api_key="market-data-test-key",
    )
    builder = SystemSnapshotBuilder(store=store, settings=s, control_plane=cp)
    view = builder.settings_view()

    assert view["system"]["llm_configured"] is True  # boolean only
    assert view["data"]["finnhub"] is True
    raw = str(view)
    assert "provider-test-key" not in raw and "market-data-test-key" not in raw
    assert view["autonomy"] == "SUPERVISED"  # Phase 3.1: fail-closed default
