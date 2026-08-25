"""Evaluation Plane (§14) + Promotion/Rollback (§21/§22) tests.

The fail-closed contract:
- small samples => INCONCLUSIVE, regardless of margin
- promotion requires a PASS EvaluationRecord — a human CANNOT overrule
  FAIL/INCONCLUSIVE evidence
- every promotion registers a rollback target through the kernel controllers
"""

import asyncio
from pathlib import Path

import pytest

from core.challenger import ChallengeRegistry, ChallengerTrial, TrialResult, TrialState
from core.control_plane import ControlPlane
from core.event_bus import InMemoryEventBus
from core.persistence import SqliteMemoryStore
from core.risk_governor import RiskGovernor
from kernel.bootstrap import create_kernel
from research.evaluation import (
    EvaluationVerdict,
    evaluate_model_walk_forward,
    evaluate_trial,
)
from simulation.generate_golden_data import write_dataset
from simulation.replay_runner import ReplayRunner


class _Memory:
    def __init__(self) -> None:
        self.events: list[tuple[str, object, dict]] = []

    def append_event(self, kind: str, ref_id: object, payload: dict) -> int:
        self.events.append((kind, ref_id, payload))
        return len(self.events)

    def iter_event_payloads(self, kind: str) -> list[dict]:
        return [p for k, _, p in self.events if k == kind]


# ------------------------------------------------------------------ verdicts


def test_small_samples_are_inconclusive_regardless_of_margin() -> None:
    record = evaluate_trial(
        champion_trades=2,
        challenger_trades=3,
        metric="pnl",
        champion_value=100.0,
        challenger_value=9999.0,
        trial_name="t",
    )
    assert record.verdict is EvaluationVerdict.INCONCLUSIVE
    assert "insufficient" in record.summary.lower()


def test_clear_superiority_passes_and_inferiority_fails() -> None:
    win = evaluate_trial(20, 20, "pnl", 100.0, 250.0, "win")
    assert win.verdict is EvaluationVerdict.PASS
    loss = evaluate_trial(20, 20, "pnl", 300.0, 100.0, "loss")
    assert loss.verdict is EvaluationVerdict.FAIL


def test_model_verdict_gates_on_sample_accuracy_calibration() -> None:
    inconclusive = evaluate_model_walk_forward(
        "m:v1", {"wf_accuracy_pct": 70.0, "wf_brier": 0.4, "wf_n_predictions": 10}
    )
    assert inconclusive.verdict is EvaluationVerdict.INCONCLUSIVE

    passing = evaluate_model_walk_forward(
        "m:v1", {"wf_accuracy_pct": 58.0, "wf_brier": 0.45, "wf_n_predictions": 80}
    )
    assert passing.verdict is EvaluationVerdict.PASS

    failing = evaluate_model_walk_forward(
        "m:v1", {"wf_accuracy_pct": 48.0, "wf_brier": 0.7, "wf_n_predictions": 80}
    )
    assert failing.verdict is EvaluationVerdict.FAIL


# ------------------------------------------------------------ promotion gates


def _evaluated_registry(tmp_path: Path, trades: int, champ_pnl: float, chall_pnl: float):
    store = SqliteMemoryStore(tmp_path / "c.db")
    kernel = create_kernel()
    registry = ChallengeRegistry(store, kernel.promotions, kernel.rollbacks)
    registry.propose("trial-x", metric="pnl")
    trial: ChallengerTrial = registry.trials["trial-x"]
    trial.state = TrialState.EVALUATED
    trial.evaluated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
    trial.champion = TrialResult("champion", trades, champ_pnl, 55.0, 2.0)
    trial.challenger = TrialResult("challenger", trades, chall_pnl, 60.0, 1.5)
    # run the same record-building path as registry.evaluate
    from research.evaluation import evaluate_trial as et

    trial.evaluation = et(
        trades, trades, "pnl", champ_pnl, chall_pnl, "trial-x"
    )
    return kernel, registry


def test_promotion_denied_without_evaluation_record(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "c.db")
    registry = ChallengeRegistry(store)
    registry.propose("bare")
    registry.trials["bare"].state = TrialState.EVALUATED
    with pytest.raises(PermissionError, match="no EvaluationRecord"):
        registry.promote("bare", "op-1")


def test_human_cannot_overrule_fail_or_inconclusive(tmp_path: Path) -> None:
    for trades, champ, chall in ((3, 0.0, 999.0), (25, 500.0, 100.0)):
        kernel, registry = _evaluated_registry(tmp_path / f"g{trades}{champ}", trades, champ, chall)
        expected = registry.trials["trial-x"].evaluation.verdict
        assert expected is not EvaluationVerdict.PASS
        with pytest.raises(PermissionError, match="cannot overrule"):
            registry.promote("trial-x", "op-god")


def test_pass_evaluation_promotes_with_receipt_and_rollback_target(tmp_path: Path) -> None:
    kernel, registry = _evaluated_registry(tmp_path, 25, 100.0, 400.0)
    result = registry.promote("trial-x", "op-1")
    assert result["promoted"] is True

    # kernel promotion controller holds the receipt trail; rollback registered
    record = kernel.promotions.get("trial", "trial-x", "challenger")
    assert record.state.value == "PROMOTED"
    target = kernel.rollbacks.get_rollback("trial", "trial-x")
    assert target.rollback_version == "baseline"
    receipts = kernel.receipts.by_object("trial", "trial-x")
    assert any(r.requested_action.startswith("promote:") for r in receipts)


# --------------------------------------------------------- control plane path


def test_promote_model_action_fail_closed_then_success(tmp_path: Path) -> None:
    write_dataset(tmp_path / "golden", symbols=["SPY"], total_bars=150)
    runner = ReplayRunner(
        csv_path_by_symbol={"SPY": tmp_path / "golden" / "SPY_1d.csv"},
        store_path=tmp_path / "m.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
    )
    asyncio.run(runner.run())
    plane = ControlPlane(
        store=runner.store,
        event_bus=InMemoryEventBus(),
        risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
        strategy_agent=None,
        order_manager=None,
        challenge_registry=runner.build_challenge_registry(),
        kernel_bridge=runner.kernel_bridge,
    )

    async def _flow() -> None:
        models = runner.kernel_bridge.kernel.models

        # 1) unknown model -> ValueError
        with pytest.raises(ValueError):
            await plane.execute(
                "op", "RISK_ADMIN", "promote_model",
                {"model_id": "ghost", "version": "v1"},
            )

        # 2) failing metrics cannot be promoted even by admin
        models.mark_evaluated(
            "direction_logreg", "v1",
            {"wf_accuracy_pct": 40.0, "wf_brier": 0.8, "wf_n_predictions": 100},
        )
        with pytest.raises(PermissionError, match="FAIL"):
            await plane.execute(
                "op", "RISK_ADMIN", "promote_model",
                {"model_id": "direction_logreg", "version": "v1"},
            )

        # 3) genuinely PASSing evidence -> promotion succeeds with rollback target
        models.mark_evaluated(
            "direction_logreg", "v1",
            {"wf_accuracy_pct": 58.0, "wf_brier": 0.45, "wf_n_predictions": 80},
        )
        result = await plane.execute(
            "op", "RISK_ADMIN", "promote_model",
            {"model_id": "direction_logreg", "version": "v1"},
        )
        assert result["result"]["promoted"] is True
        assert result["result"]["rollback_target"] == "deterministic_baseline:v1"

        mv = models.get("direction_logreg", "v1")
        assert mv.status.value == "PROMOTED"
        target = runner.kernel_bridge.kernel.rollbacks.get_rollback(
            "model", "direction_logreg"
        )
        assert target.rollback_version == "deterministic_baseline:v1"

        # 4) VIEWER denied outright
        with pytest.raises(PermissionError):
            await plane.execute(
                "viewer", "VIEWER", "promote_model",
                {"model_id": "direction_logreg", "version": "v1"},
            )

    asyncio.run(_flow())

    records = runner.store.iter_event_payloads("EVALUATION_RECORD")
    assert records, "evaluation records must be audited"


def test_challenger_evaluation_attaches_record_and_endpoint_serves_it(
    tmp_path: Path,
) -> None:
    write_dataset(tmp_path / "golden", symbols=["SPY"], total_bars=90)
    runner = ReplayRunner(
        csv_path_by_symbol={"SPY": tmp_path / "golden" / "SPY_1d.csv"},
        store_path=tmp_path / "e.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
        settings=__import__("core.config", fromlist=["Settings"]).Settings(
            model_provider="none", auto_research=False
        ),
    )
    asyncio.run(runner.run())
    registry = runner.build_challenge_registry()
    registry.propose("manual:x", metric="pnl")
    asyncio.run(runner.evaluate_challenger("manual:x"))

    trial = registry.trials["manual:x"]
    assert trial.evaluation is not None
    assert trial.evaluation.verdict in {
        EvaluationVerdict.PASS,
        EvaluationVerdict.FAIL,
        EvaluationVerdict.INCONCLUSIVE,
    }

    view = runner.build_snapshot_builder().evaluations_view()
    assert any(r["subject_type"] == "trial" for r in view)
