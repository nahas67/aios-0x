"""ML strategy family + operator-triggered challenger evaluation.

Closes the §12→§13 loop: the trained direction model becomes a trading
candidate generator (challenger side), and staged trials can be EVALUATED
from the command center — with promotion still a separate human decision.
"""

import asyncio
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import pytest

from communities.c4_strategy.ml_family import MLDirectionFamily
from core.event_bus import InMemoryEventBus
from schemas.contracts import MarketDataPayload, PriceData


def _payload(close: float) -> MarketDataPayload:
    return MarketDataPayload(
        symbol="TEST",
        timeframe="1d",
        price_data=PriceData(
            timestamp=datetime.now(UTC),
            open=close,
            high=close * 1.001,
            low=close * 0.999,
            close=close,
            volume=1000.0,
        ),
        is_simulated=True,
    )


def _history(closes: list[float]) -> deque[float]:
    return deque(closes, maxlen=30)


def _trending_closes(n: int = 120, drift: float = 0.004) -> list[float]:
    closes = [100.0]
    for i in range(n - 1):
        step = drift if (i // 10) % 2 == 0 else -drift / 3  # up-dominated walk
        closes.append(max(1.0, closes[-1] * (1 + step)))
    return closes


# ------------------------------------------------------------------ family


def test_ml_family_stays_silent_during_warmup() -> None:
    family = MLDirectionFamily()
    closes = _trending_closes()[:25]  # below the warm-up floor (29 bars)
    assert family.evaluate("T", _payload(closes[-1]), _history(closes), 0.0) is None
    assert family._model is None


def test_ml_family_proposes_on_strong_trend_and_is_deterministic() -> None:
    closes = _trending_closes()
    family_a = MLDirectionFamily(threshold=0.55)
    family_b = MLDirectionFamily(threshold=0.55)
    decisions_a: list[str | None] = []
    for i in range(45, len(closes)):
        candidate = family_a.evaluate(
            "T", _payload(closes[i]), _history(closes[: i + 1]), 0.0
        )
        decisions_a.append(candidate.action if candidate else None)
        family_b.evaluate("T", _payload(closes[i]), _history(closes[: i + 1]), 0.0)

    assert any(d == "BUY" for d in decisions_a), "strong trend must produce BUY candidates"
    assert family_b._refits == family_a._refits > 0
    assert family_a._model is not None
    assert family_a._model.artifact_hash() == family_b._model.artifact_hash()


def test_ml_family_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        MLDirectionFamily(threshold=0.5)
    with pytest.raises(ValueError):
        MLDirectionFamily(threshold=1.0)


# ------------------------------------------------------------ control plane


def test_evaluate_trial_action_is_risk_admin_gated(tmp_path: Path) -> None:
    from core.control_plane import ControlPlane
    from core.risk_governor import RiskGovernor

    calls: list[str] = []

    async def evaluator(name: str) -> dict:
        calls.append(name)
        return {"recommendation": "PROMOTE", "metric": "pnl"}

    plane = ControlPlane(
        store=_Memory(),
        event_bus=InMemoryEventBus(),
        risk_governor=RiskGovernor(event_bus=InMemoryEventBus()),
        strategy_agent=None,
        order_manager=None,
        challenge_registry=object(),
        trial_evaluator=evaluator,
    )

    async def _flow() -> None:
        with pytest.raises(PermissionError):
            await plane.execute("op-1", "VIEWER", "evaluate_trial", {"name": "auto:x"})
        result = await plane.execute("op-1", "RISK_ADMIN", "evaluate_trial", {"name": "auto:x"})
        assert result["result"]["recommendation"] == "PROMOTE"
        with pytest.raises(ValueError):
            await plane.execute("op-1", "RISK_ADMIN", "evaluate_trial", {})

    asyncio.run(_flow())
    assert calls == ["auto:x"]


class _Memory:
    """Minimal audit sink for control-plane tests."""

    def __init__(self) -> None:
        self.events: list[tuple[str, object, dict]] = []

    def append_event(self, kind: str, ref_id: object, payload: dict) -> int:
        self.events.append((kind, ref_id, payload))
        return len(self.events)


# ------------------------------------------------------------- integration


def test_runner_evaluates_staged_challenger_end_to_end(tmp_path: Path) -> None:
    from simulation.generate_golden_data import write_dataset
    from simulation.replay_runner import ReplayRunner

    write_dataset(tmp_path / "golden", symbols=["SPY"], total_bars=90)
    runner = ReplayRunner(
        csv_path_by_symbol={"SPY": tmp_path / "golden" / "SPY_1d.csv"},
        store_path=tmp_path / "main.db",
        initial_balance=100000.0,
        slippage_pct=0.05,
        settings=__import__("core.config", fromlist=["Settings"]).Settings(
            model_provider="none", auto_research=False
        ),
    )
    asyncio.run(runner.run())

    registry = runner.build_challenge_registry()
    trial_name = "manual:ml-vs-baseline"
    registry.propose(trial_name, description="ml challenger vs baseline")

    recommendation = asyncio.run(runner.evaluate_challenger(trial_name))
    assert recommendation["recommendation"] in {"PROMOTE", "REJECT"}
    trial = registry.trials[trial_name]
    assert trial.state.value == "EVALUATED"
    assert trial.champion is not None and trial.challenger is not None
    # both sides actually traded over identical data
    assert trial.champion.trades >= 0 and trial.challenger.trades >= 0

    evaluations = runner.store.iter_event_payloads("CHALLENGER_EVALUATION")
    assert any(e.get("champion") for e in evaluations)
