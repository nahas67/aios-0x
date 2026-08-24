"""Phase 2 Intelligence Onboarding tests: gateway, router, debate, verification, prompt lab."""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from communities.c2_research.debate_engine import (
    BullBearCase,
    DebateEngine,
)
from communities.c3_verification.verification_agent import (
    VerificationAgent,
    cited_numbers,
)
from core.config import Settings
from core.event_bus import InMemoryEventBus
from core.model_gateway import (
    ChatMessage,
    DecodeError,
    ModelRequest,
    OpenAICompatibleGateway,
    ScriptedModel,
    build_gateway,
    complete_structured,
    extract_json_block,
)
from core.model_router import ModelRouter, TaskTier
from core.prompts import PromptRegistry, PromptSpec
from evaluation.prompt_lab import EvalCase, evaluate_prompt
from schemas.contracts import (
    CandidateHypothesis,
    EvidencePack,
    MarketDataPayload,
    NewsSentiment,
    PriceData,
)


class _Tiny(BaseModel):
    a: int


# --------------------------------------------------------------------- gateway


def test_build_gateway_honest_none_without_credentials() -> None:
    s = Settings(model_provider="none")
    assert build_gateway(s) is None
    s2 = Settings(model_provider="openai", openai_api_key=None)
    assert build_gateway(s2) is None


def test_openai_gateway_requires_key() -> None:
    with pytest.raises(RuntimeError, match="API key"):
        OpenAICompatibleGateway(
            api_key="", base_url="http://x", default_model="m", settings=Settings()
        )


def test_extract_json_block_tolerates_fences() -> None:
    text = '```json\n{"a": 5}\n```'
    assert json.loads(extract_json_block(text))["a"] == 5
    with pytest.raises(DecodeError):
        extract_json_block("no json here")


def test_structured_decode_repairs_once() -> None:
    responses = iter(["not json at all", '{"a": 7}'])
    sm = ScriptedModel(lambda r: next(responses))
    out, resp = asyncio.run(
        complete_structured(sm, _Tiny, [ChatMessage(role="user", content="go")], Settings())
    )
    assert out.a == 7
    assert len(sm.requests) == 2  # original + repair retry
    # Repair conversation included the validation error feedback
    repair_msg = sm.requests[1].messages[-1].content
    assert "violated the schema" in repair_msg


def test_structured_decode_exhaustion_raises() -> None:
    sm = ScriptedModel(lambda r: "garbage")
    with pytest.raises(DecodeError):
        asyncio.run(
            complete_structured(
                sm, _Tiny, [ChatMessage(role="user", content="go")], Settings(), max_retries=1
            )
        )


def test_router_honest_unavailable_and_tiers() -> None:
    router = ModelRouter(None, Settings())
    decision = router.resolve(TaskTier.CHEAP)
    assert decision.available is False
    assert "deterministic" in decision.reason

    router2 = ModelRouter(ScriptedModel(lambda r: ""), Settings())
    d_cheap = router2.resolve(TaskTier.CHEAP)
    d_reason = router2.resolve(TaskTier.REASONING)
    assert d_cheap.available and d_reason.available
    assert d_cheap.model_id != d_reason.model_id or d_cheap.model_id is not None


def test_prompt_spec_variable_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="template vars"):
        PromptSpec(prompt_id="x", template="Hello {{name}}", variables=["wrong"])


# ---------------------------------------------------------------------- debate


def _debate_responder(request: ModelRequest) -> str:
    content = request.messages[0].content
    if "Value Investor" in content:
        return '{"assessment": "Margin of safety adequate at this level.", "conviction": "MEDIUM"}'
    if "Growth Investor" in content:
        return '{"assessment": "Momentum confirms growth narrative.", "conviction": "HIGH"}'
    if "Contrarian" in content:
        return '{"assessment": "Consensus is too bullish here.", "conviction": "AGAINST"}'
    if "Macro Analyst" in content:
        return '{"assessment": "Liquidity environment supportive.", "conviction": "MEDIUM"}'
    if "Bull Analyst" in content:
        return (
            '{"argument": "Momentum and sentiment favor upside continuation.", '
            '"falsifiable_claim": "Price closes higher next bar.", '
            '"cited_numbers": []}'
        )
    if "Bear Analyst" in content:
        return (
            '{"argument": "Range expansion warns of reversal risk.", '
            '"falsifiable_claim": "Price closes lower next bar.", '
            '"cited_numbers": []}'
        )
    if "Quant Reviewer" in content:
        return '{"weaknesses": ["single-bar sample size"], "verdict": "PROCEED"}'
    if "Debate Moderator" in content:
        return (
            '{"supporting_arguments": ["Momentum favors continuation", '
            '"Sentiment aligns with bids"], '
            '"counter_arguments": ["Single-bar sample size", "Reversal risk"], '
            '"expected_risk_reward_ratio": 2.0}'
        )
    return "not json"


def _payload() -> MarketDataPayload:
    return MarketDataPayload(
        symbol="BTC/USD",
        timeframe="1d",
        price_data=PriceData(open=100.0, high=102.0, low=98.0, close=101.0, volume=1500.0),
        news_sentiment=[NewsSentiment(title="t", sentiment_score=0.5, source="x")],
        is_simulated=True,
    )


def test_debate_llm_path_produces_balanced_hypothesis() -> None:
    router = ModelRouter(ScriptedModel(_debate_responder), Settings())
    engine = DebateEngine(router, PromptRegistry(), Settings())

    result = asyncio.run(engine.debate(_payload()))

    assert result.transcript.used_llm is True
    assert result.transcript.fell_back is False
    assert result.hypothesis is not None
    h = result.hypothesis
    assert len(h.supporting_arguments) >= 2
    assert len(h.counter_arguments) >= 2  # Mandatory Balance Rule
    assert h.expected_risk_reward_ratio >= 1.5
    roles = [t.role for t in result.transcript.turns]
    assert roles == ["BULL", "BEAR", "VALUE", "GROWTH", "CONTRARIAN", "MACRO", "QUANT", "MODERATOR"]


def test_debate_falls_back_without_gateway() -> None:
    router = ModelRouter(None, Settings())
    engine = DebateEngine(router, PromptRegistry(), Settings())
    result = asyncio.run(engine.debate(_payload()))
    assert result.transcript.fell_back is True
    assert result.hypothesis is not None
    assert result.hypothesis.expected_risk_reward_ratio == 2.0


def test_debate_falls_back_on_garbage_output() -> None:
    router = ModelRouter(ScriptedModel(lambda r: "total nonsense"), Settings())
    engine = DebateEngine(router, PromptRegistry(), Settings())
    result = asyncio.run(engine.debate(_payload()))
    assert result.transcript.fell_back is True
    assert "DecodeError" in (result.transcript.fallback_reason or "")


# ---------------------------------------------------------------- verification


def test_verification_numeric_consistency_gating() -> None:
    payload = _payload()
    evidence = EvidencePack.from_payload(payload)

    async def _run(hyp: CandidateHypothesis) -> tuple[object, float]:
        bus = InMemoryEventBus()
        await bus.start()
        agent = VerificationAgent(bus)
        await agent.on_data_acquired(payload)
        report = await agent.verify_hypothesis(hyp)
        await bus.stop()
        return report.is_verified, report.confidence_score

    good = CandidateHypothesis(
        symbol="BTC/USD",
        thesis="Consistent claims",
        supporting_arguments=[
            f"Close {evidence.close:g} with momentum {round(evidence.momentum_pct, 2):+}%",
            f"Sentiment reading {round(evidence.sentiment_avg, 2)}",
        ],
        counter_arguments=["Reversal risk remains"],
        timeframe="1d",
        expected_risk_reward_ratio=2.0,
    )
    verified, score = asyncio.run(_run(good))
    assert verified is True and score == pytest.approx(100.0)

    bad = CandidateHypothesis(
        symbol="BTC/USD",
        thesis="Fabricated level",
        supporting_arguments=["Price stands at 999999 resistance"],
        counter_arguments=["Risk exists"],
        timeframe="1d",
        expected_risk_reward_ratio=2.0,
    )
    verified2, score2 = asyncio.run(_run(bad))
    assert verified2 is False
    assert score2 < 70.0
    assert cited_numbers(bad.supporting_arguments[0]) == [999999.0]


def test_verification_without_evidence_keeps_legacy_behavior() -> None:
    bus = InMemoryEventBus()

    async def _run() -> None:
        await bus.start()
        agent = VerificationAgent(bus)
        hyp = CandidateHypothesis(
            symbol="X/USD",
            thesis="t",
            supporting_arguments=["a", "b"],
            counter_arguments=["c"],
            timeframe="1d",
            expected_risk_reward_ratio=2.0,
        )
        report = await agent.verify_hypothesis(hyp)
        await bus.stop()
        assert report.confidence_score == 100.0
        assert report.is_verified is True

    asyncio.run(_run())


# ------------------------------------------------------------------ prompt lab


def _load_golden_cases(path: Path) -> list[EvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [EvalCase(**case) for case in data["cases"]]


def test_prompt_lab_gate_pass_and_fail(tmp_path: Path) -> None:
    golden = Path("evaluation/golden/research-bull-thesis.cases.json")
    cases = _load_golden_cases(golden)
    registry = PromptRegistry()
    settings = Settings()

    good_router = ModelRouter(ScriptedModel(_debate_responder), settings)
    result_pass = asyncio.run(
        evaluate_prompt(
            registry,
            good_router.gateway,  # type: ignore[arg-type]
            BullBearCase,
            "research-bull-thesis",
            cases,
            settings,
            tier_model=settings.research_model_cheap,
        )
    )
    assert result_pass.passed is True
    assert result_pass.parse_rate == pytest.approx(1.0)

    bad_router = ModelRouter(ScriptedModel(lambda r: "unparseable"), settings)
    result_fail = asyncio.run(
        evaluate_prompt(
            registry,
            bad_router.gateway,  # type: ignore[arg-type]
            BullBearCase,
            "research-bull-thesis",
            cases,
            settings,
            tier_model=settings.research_model_cheap,
        )
    )
    assert result_fail.passed is False
    assert result_fail.parse_rate == pytest.approx(0.0)


# ---------------------------------------------------- runner integration (LLM)


def _small_dataset(tmp_path: Path) -> dict[str, Path]:
    from simulation.generate_golden_data import write_dataset

    write_dataset(tmp_path / "golden", symbols=["BTC/USD"], total_bars=40)
    return {"BTC/USD": tmp_path / "golden" / "BTC_USD_1d.csv"}


def test_runner_debate_mode_logs_model_calls(tmp_path: Path) -> None:
    from simulation.replay_runner import ReplayRunner

    dataset = _small_dataset(tmp_path)
    gateway = ScriptedModel(_debate_responder)
    runner = ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=tmp_path / "debate.db",
        gateway=gateway,
        settings=Settings(research_mode="auto"),
    )
    summary = asyncio.run(runner.run())

    assert summary.research_mode_used == "debate"
    assert summary.model_calls > 0
    assert summary.total_model_cost_usd == 0.0  # scripted model is zero-cost

    counts = runner.store.counts()
    assert counts["event_log"] > summary.trades_closed  # includes MODEL_CALL events

    # Every model call recorded with provider accounting
    rows = runner.store._conn.execute(
        "SELECT COUNT(*) AS n FROM event_log WHERE kind='MODEL_CALL'"
    ).fetchone()
    assert rows["n"] == summary.model_calls


def test_runner_deterministic_mode_when_no_gateway(tmp_path: Path) -> None:
    from simulation.replay_runner import ReplayRunner

    dataset = _small_dataset(tmp_path)
    runner = ReplayRunner(
        csv_path_by_symbol=dataset,
        store_path=tmp_path / "det.db",
        settings=Settings(research_mode="auto"),  # no gateway injected, no env keys
    )
    summary = asyncio.run(runner.run())
    assert summary.research_mode_used == "deterministic"
    assert summary.model_calls == 0
