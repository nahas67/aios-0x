"""Re-inspection integration pass: vector-memory retrieval, roster, auto tax+CA."""

import asyncio
from pathlib import Path

import pytest

from core.agents import registered_agents
from core.vector_memory import BaseVectorMemory, InMemoryVectorMemory


def _dataset(tmp_path: Path, bars: int = 60) -> dict[str, Path]:
    from simulation.generate_golden_data import write_dataset

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=bars)
    return {"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"}


# ------------------------------------------------- multi-agent + memory wiring


def test_debate_engine_surfaces_memory_turn() -> None:
    """Provenance-linked postmortem lessons reach the moderator as context."""
    from communities.c2_research.debate_engine import DebateEngine
    from core.config import Settings
    from core.model_gateway import ScriptedModel
    from core.model_router import ModelRouter
    from core.prompts import PromptRegistry

    class MemoryShim(BaseVectorMemory):
        def __init__(self) -> None:
            self.inner = InMemoryVectorMemory()
            self.inner.upsert(
                "postmortem_lessons",
                "old-1",
                "BTC/USD BUY exit STOP_HIT pnl -7.50: thesis invalidated at stop.",
                {"family": "momentum"},
            )

        def upsert(self, *a, **k) -> None:  # pragma: no cover - read-only in this test
            pass

        def search(self, collection: str, query_text: str, k: int = 5):
            return self.inner.search(collection, query_text, k=k)

    responder = ScriptedModel(_debate_responder_any())
    router = ModelRouter(responder, Settings())
    engine = DebateEngine(router, PromptRegistry(), Settings(), memory=MemoryShim())

    from schemas.contracts import MarketDataPayload, PriceData

    payload = MarketDataPayload(
        symbol="BTC/USD",
        timeframe="1d",
        price_data=PriceData(open=100.0, high=102.0, low=98.0, close=101.0, volume=1500.0),
        is_simulated=True,
    )
    result = asyncio.run(engine.debate(payload))

    roles = [t.role for t in result.transcript.turns]
    assert "MEMORY" in roles, f"expected MEMORY context turn, got {roles}"
    assert result.transcript.used_llm is True
    assert any("STOP_HIT" in t.content for t in result.transcript.turns if t.role == "MEMORY")


def _debate_responder_any():
    def responder(request) -> str:
        content = request.messages[0].content
        if "Bull Analyst" in content:
            return (
                '{"argument": "Upside continuation case.", '
                '"falsifiable_claim": "Higher close next bar.", "cited_numbers": []}'
            )
        if "Bear Analyst" in content:
            return (
                '{"argument": "Reversal risk dominates.", '
                '"falsifiable_claim": "Lower close next bar.", "cited_numbers": []}'
            )
        if "Quant Reviewer" in content:
            return '{"weaknesses": ["tiny sample"], "verdict": "PROCEED"}'
        if "Debate Moderator" in content:
            return (
                '{"supporting_arguments": ["Momentum persists", "Sentiment aligned"], '
                '"counter_arguments": ["Tiny sample", "Reversal risk"], '
                '"expected_risk_reward_ratio": 2.0}'
            )
        return "junk"

    return responder


# ---------------------------------------------------------------- runner wiring


def test_runner_registers_roster_and_upserts_memory(tmp_path: Path) -> None:
    from simulation.replay_runner import ReplayRunner

    runner = ReplayRunner(
        csv_path_by_symbol=_dataset(tmp_path),
        store_path=tmp_path / "int.db",
    )
    summary = asyncio.run(runner.run())
    assert summary.trades_closed >= 1

    agents = registered_agents(runner.store)
    for expected in ("c2-research", "c9-governor", "risk-governor", "c11-finance"):
        assert expected in agents, f"missing roster entry {expected}"

    # Semantic memory holds one lesson per closed trade
    hits = runner.vector_memory.search("postmortem_lessons", "exit pnl", k=50)
    assert len(hits) >= summary.trades_closed


def test_auto_tax_computation_and_ca_gate(tmp_path: Path) -> None:
    from simulation.replay_runner import ReplayRunner

    runner = ReplayRunner(
        csv_path_by_symbol=_dataset(tmp_path),
        store_path=tmp_path / "tax.db",
    )
    summary = asyncio.run(runner.run())
    assert summary.trades_closed >= 1

    computations = runner.store.iter_event_payloads("TAX_COMPUTATION")
    assert len(computations) == 1, "exactly one aggregated advisory computation"
    comp = computations[0]
    assert comp["requires_professional_signoff"] is True
    assert comp["rule_id"] == "GENERIC_25"

    items = list(runner.ca_workflow.items.values())
    assert len(items) == 1
    item = items[0]
    assert item.subject_kind == "tax_computation"
    assert item.state.value == "PREPARED"

    # Filing gate holds without a human reviewer
    with pytest.raises(PermissionError, match="APPROVED_BY_CA"):
        runner.ca_workflow.export_for_filing(item.item_id)
