"""Operator console tests: human-held gate visibility + user-driven chat.

The chat bot holds NO authority: queries come from read-only views, commands
run through the audited ControlPlane with the operator's own role. The gates
view makes the constitution's §5 human-held production controls visible and
user-controllable.
"""

import asyncio
from pathlib import Path

from core.chat_console import OperatorChat
from core.control_plane import ControlPlane
from core.event_bus import InMemoryEventBus
from core.persistence import SqliteMemoryStore
from core.risk_governor import RiskGovernor
from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner


class _Memory:
    def __init__(self) -> None:
        self.events: list[tuple[str, object, dict]] = []

    def append_event(self, kind: str, ref_id: object, payload: dict) -> int:
        self.events.append((kind, ref_id, payload))
        return len(self.events)


def _plane(store=None, **extra) -> ControlPlane:
    return ControlPlane(
        store=store or _Memory(),
        event_bus=InMemoryEventBus(),
        risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
        strategy_agent=None,
        order_manager=None,
        **extra,
    )


# ------------------------------------------------------------------- gates


def test_gates_view_reports_blockers_and_approval(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "g.db")
    plane, builder = _plane_and_builder(store)

    view = builder.gates_view()
    by_id = {g["gate"]: g for g in view["gates"]}
    assert by_id["broker_testnet"]["status"] == "BLOCKED"
    assert "testnet adapter wiring" in by_id["broker_testnet"]["how_to_unblock"]
    assert by_id["tax_signoff"]["status"] == "BLOCKED"
    assert by_id["live_capital"]["status"] == "BLOCKED"
    assert view["production_allowed"] is False

    # the user flips the capital gate through the audited control action
    asyncio.run(
        plane.execute("principal", "ADMIN", "approve_live_capital", {"note": "board minute 7"})
    )
    view2 = builder.gates_view()
    capital = next(g for g in view2["gates"] if g["gate"] == "live_capital")
    assert capital["status"] == "RECORDED"
    assert view2["live_routing_enabled"] is False
    assert view2["live_capital_approved_by"] == "principal"


def _plane_and_builder(store=None, **extra):
    from api.views import SystemSnapshotBuilder

    store = store or _Memory()
    plane = ControlPlane(
        store=store,
        event_bus=InMemoryEventBus(),
        risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
        strategy_agent=None,
        order_manager=None,
        **extra,
    )
    if isinstance(store, SqliteMemoryStore):
        builder = SystemSnapshotBuilder(
            store=store,
            control_plane=plane,
            ca_workflow=None,
        )
    else:
        builder = SystemSnapshotBuilder(
            store=SqliteMemoryStore(Path(__import__("tempfile").mkdtemp()) / "v.db"),
            control_plane=plane,
            ca_workflow=None,
        )
    return plane, builder


def _builder_with_plane(plane):
    return _plane_and_builder()[1]


# -------------------------------------------------------------------- chat


def test_chat_query_routes_to_readonly_views(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "c.db")
    store.append_event("EVALUATION_RECORD", "ev-1", {"verdict": "PASS", "subject_type": "model"})
    _plane, builder = _plane_and_builder(store)

    async def _flow() -> None:
        chat = OperatorChat(builder, None)  # queries need no control plane
        pnl = await chat.ask("op", "VIEWER", "what is my pnl")
        assert pnl["kind"] == "query" and pnl["query"] == "P&L analysis"

        evals = await chat.ask("op", "VIEWER", "show evaluations")
        assert evals["data"][0]["verdict"] == "PASS"

        gates = await chat.ask("op", "VIEWER", "what gates block production?")
        blocked = [g["gate"] for g in gates["data"]["gates"] if g["status"] != "APPROVED"]
        assert "tax_signoff" in blocked

    asyncio.run(_flow())


def test_chat_commands_run_through_rbac_and_audit(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "cmd.db")
    plane, builder = _plane_and_builder(store)
    chat = OperatorChat(builder, plane)

    async def _flow() -> None:
        # VIEWER cannot pause trading — the bot does not grant authority
        denied = await chat.ask("op", "VIEWER", "pause trading")
        assert denied["kind"] == "denied"
        assert "may not perform" in denied["answer"]

        ok = await chat.ask("op-2", "OPERATOR", "pause trading")
        assert ok["kind"] == "command" and ok["result"]["paused"] is True

        autonomy = await chat.ask("op-2", "RISK_ADMIN", "set autonomy supervised")
        assert autonomy["result"]["autonomy"] == "SUPERVISED"

        unknown = await chat.ask("op", "VIEWER", "tell me a joke")
        assert unknown["kind"] == "help"

    asyncio.run(_flow())

    control_events = store.iter_event_payloads("CONTROL_ACTION")
    assert any(e.get("authorized") for e in control_events)
    assert any(not e.get("authorized") for e in control_events)


def test_promote_model_via_chat_end_to_end(tmp_path: Path) -> None:
    write_dataset(tmp_path / "golden", symbols=["SPY"], total_bars=150)
    runner = ReplayRunner(
        csv_path_by_symbol={"SPY": tmp_path / "golden" / "SPY_1d.csv"},
        store_path=tmp_path / "m.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
    )
    asyncio.run(runner.run())
    plane = runner.build_control_plane()
    models = runner.kernel_bridge.kernel.models
    models.mark_evaluated(
        "direction_logreg", "v1",
        {"wf_accuracy_pct": 58.0, "wf_brier": 0.45, "wf_n_predictions": 80},
    )
    chat = OperatorChat(runner.build_snapshot_builder(), plane)

    result = asyncio.run(
        chat.ask("principal", "RISK_ADMIN", "promote model direction_logreg")
    )
    assert result["kind"] == "command"
    assert result["result"]["promoted"] is True
    assert result["result"]["rollback_target"] == "deterministic_baseline:v1"
