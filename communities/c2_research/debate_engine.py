"""Community 2: Adversarial debate engine - Bull vs Bear vs Quant vs Moderator.

Replaces the template hypothesis generator when a model gateway is configured
(research_mode=auto). Honesty rules:

- Every cited number in debate prompts comes from the market snapshot; the
  verification firewall re-checks numerics independently (defense in depth).
- Any gateway failure (unavailable, HTTP, decode-after-retries) falls back to
  the deterministic template researcher, clearly tagged in the transcript -
  the system never pretends an LLM contributed.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from core.config import Settings
from core.event_bus import BaseEventBus, EventTopic
from core.model_gateway import (
    ChatMessage,
    DecodeError,
    GatewayHTTPError,
    ModelResponse,
    ModelUnavailableError,
    complete_structured,
)
from core.model_router import ModelRouter, TaskTier
from core.prompts import PromptRegistry
from schemas.contracts import (
    CandidateHypothesis,
    MarketDataPayload,
    generate_uuid,
)

logger = logging.getLogger(__name__)

_MIN_RR = 1.5

ModelCallSink = Callable[[str, ModelResponse], Awaitable[None]]


class BullBearCase(BaseModel):
    argument: str = Field(min_length=1)
    falsifiable_claim: str = Field(min_length=1)
    cited_numbers: list[float] = Field(default_factory=list)


class QuantVerdict(BaseModel):
    weaknesses: list[str] = Field(default_factory=list)
    verdict: str = Field(pattern="^(PROCEED|REJECT)$")


class PersonalityAssessment(BaseModel):
    assessment: str = Field(min_length=1)
    conviction: str = Field(pattern="^(HIGH|MEDIUM|LOW|AGAINST)$")


class ModeratorSynthesis(BaseModel):
    supporting_arguments: list[str] = Field(min_length=2)
    counter_arguments: list[str] = Field(min_length=2)
    expected_risk_reward_ratio: float = Field(gt=0.0)


class DebateTurn(BaseModel):
    role: str
    content: str
    model: str | None = None
    provider: str | None = None


class DebateTranscript(BaseModel):
    transcript_id: str = Field(default_factory=generate_uuid)
    symbol: str
    timeframe: str
    turns: list[DebateTurn] = Field(default_factory=list)
    used_llm: bool = False
    fell_back: bool = False
    fallback_reason: str | None = None
    total_cost_usd: float = 0.0


class DebateResult(BaseModel):
    hypothesis: CandidateHypothesis | None
    transcript: DebateTranscript


def snapshot_vars(payload: MarketDataPayload) -> dict[str, str]:
    """Deterministic market-snapshot variables shared by debate prompts."""
    price = payload.price_data
    momentum = (price.close - price.open) / price.open * 100.0
    bar_range = (price.high - price.low) / price.open * 100.0
    sentiment = 0.0
    if payload.news_sentiment:
        sentiment = sum(s.sentiment_score for s in payload.news_sentiment) / len(
            payload.news_sentiment
        )
    return {
        "symbol": payload.symbol,
        "timeframe": payload.timeframe,
        "close": f"{price.close:g}",
        "momentum_pct": f"{momentum:+.2f}",
        "range_pct": f"{bar_range:.2f}",
        "sentiment": f"{sentiment:.2f}",
    }


def _deterministic_hypothesis(payload: MarketDataPayload) -> CandidateHypothesis:
    """Template researcher (pre-Phase-2 behavior), used as honest fallback."""
    price = payload.price_data
    momentum = (price.close - price.open) / price.open * 100.0
    sentiment = 0.0
    if payload.news_sentiment:
        sentiment = sum(s.sentiment_score for s in payload.news_sentiment) / len(
            payload.news_sentiment
        )
    return CandidateHypothesis(
        symbol=payload.symbol,
        thesis=(
            f"Deterministic-fallback hypothesis for {payload.symbol} ({payload.timeframe}): "
            f"close={price.close} ({momentum:+.2f}%), avg sentiment={sentiment:.2f}."
        ),
        supporting_arguments=[
            (
                f"Bullish price movement on {payload.timeframe} timeframe with {momentum:+.2f}% move"
                if momentum >= 0
                else f"Bearish pressure on {payload.timeframe} timeframe ({momentum:+.2f}% move)"
            ),
            f"News sentiment reading {sentiment:+.2f}",
        ],
        counter_arguments=[
            f"Macro uncertainty and volatility risk on {payload.symbol}",
            "Potential false breakout or liquidity squeeze",
        ],
        timeframe=payload.timeframe,
        expected_risk_reward_ratio=2.0,
    )


class DebateEngine:
    """Orchestrates one adversarial research cycle for a market snapshot."""

    def __init__(
        self,
        router: ModelRouter,
        registry: PromptRegistry,
        settings: Settings,
        model_call_sink: ModelCallSink | None = None,
        memory: Any = None,
    ) -> None:
        """``memory`` is an optional BaseVectorMemory (core boundary, allowed)
        used to surface similar past postmortem lessons to the moderator."""
        self._router = router
        self._registry = registry
        self._settings = settings
        self._sink = model_call_sink
        self._memory = memory

    async def _call_model(
        self,
        contract: type[BaseModel],
        prompt_text: str,
        tier: str,
    ) -> tuple[BaseModel, ModelResponse]:
        decision = self._router.resolve(tier)
        assert self._router.gateway is not None and decision.available
        return await complete_structured(
            gateway=self._router.gateway,
            contract=contract,
            messages=[ChatMessage(role="user", content=prompt_text)],
            settings=self._settings,
            model_hint=decision.model_id,
        )

    def _record(
        self,
        transcript: DebateTranscript,
        role: str,
        content: Any,
        model: str | None = None,
        provider: str | None = None,
        response: ModelResponse | None = None,
    ) -> None:
        if response is not None:
            transcript.turns.append(
                DebateTurn(
                    role=role,
                    content=response.content,
                    model=response.model,
                    provider=response.provider,
                )
            )
            transcript.total_cost_usd = round(transcript.total_cost_usd + response.cost_usd, 8)
        else:
            transcript.turns.append(
                DebateTurn(role=role, content=str(content), model=model, provider=provider)
            )

    async def _emit_sink(self, role: str, response: ModelResponse) -> None:
        if self._sink:
            await self._sink(role.lower(), response)

    async def debate(self, payload: MarketDataPayload) -> DebateResult:
        transcript = DebateTranscript(symbol=payload.symbol, timeframe=payload.timeframe)

        if not self._router.llm_available:
            transcript.fell_back = True
            transcript.fallback_reason = "no gateway configured"
            return DebateResult(
                hypothesis=_deterministic_hypothesis(payload), transcript=transcript
            )

        v = snapshot_vars(payload)
        try:
            # FIX 1: BULL and BEAR are independent -> run in parallel.
            bull_spec = self._registry.get("research-bull-thesis")
            bear_spec = self._registry.get("research-bear-thesis")
            (bull_raw, bull_resp), (bear_raw, bear_resp) = await asyncio.gather(
                self._call_model(BullBearCase, bull_spec.render(**v), TaskTier.CHEAP),
                self._call_model(BullBearCase, bear_spec.render(**v), TaskTier.CHEAP),
            )
            bull: BullBearCase = bull_raw  # type: ignore[assignment]
            bear: BullBearCase = bear_raw  # type: ignore[assignment]
            self._record(transcript, "BULL", bull_resp)
            await self._emit_sink("BULL", bull_resp)
            self._record(transcript, "BEAR", bear_resp)
            await self._emit_sink("BEAR", bear_resp)

            # Personality agents: 4 independent lenses run in parallel
            personality_ids = [
                ("VALUE", "research-value-investor"),
                ("GROWTH", "research-growth-investor"),
                ("CONTRARIAN", "research-contrarian"),
                ("MACRO", "research-macro-analyst"),
            ]
            personality_results = await asyncio.gather(
                *[
                    self._call_model(
                        PersonalityAssessment,
                        self._registry.get(pid).render(**v),
                        TaskTier.CHEAP,
                    )
                    for _, pid in personality_ids
                ]
            )
            for (role, _pid), (raw, resp) in zip(personality_ids, personality_results):
                assessment: PersonalityAssessment = raw  # type: ignore[assignment]
                self._record(
                    transcript,
                    role,
                    f"{assessment.assessment} [{assessment.conviction}]",
                    model=resp.model,
                    provider=resp.provider,
                )
                transcript.total_cost_usd = round(transcript.total_cost_usd + resp.cost_usd, 8)
                await self._emit_sink(role.lower(), resp)

            quant_raw = await self._ask(
                QuantVerdict,
                self._registry.get("research-quant-review").render(
                    bull_argument=bull.argument, bear_argument=bear.argument
                ),
                TaskTier.CHEAP,
                "QUANT",
                transcript,
            )
            quant: QuantVerdict = quant_raw  # type: ignore[assignment]

            memory_context = ""
            if self._memory is not None:
                try:
                    hits = self._memory.search(
                        "postmortem_lessons",
                        f"{payload.symbol} {v['momentum_pct']} momentum {v['sentiment']} sentiment",
                        k=2,
                    )
                    lessons = [h.text for h in hits if h.score > 0.05]
                    if lessons:
                        memory_context = "; ".join(lessons)
                        transcript.turns.append(
                            DebateTurn(
                                role="MEMORY",
                                content=memory_context,
                                model=None,
                                provider="vector_memory",
                            )
                        )
                except Exception as exc:  # noqa: BLE001 - memory must never break research
                    logger.warning("memory retrieval skipped: %s", exc)

            synthesis_raw = await self._ask(
                ModeratorSynthesis,
                self._registry.get("research-moderator-synthesis").render(
                    symbol=v["symbol"],
                    timeframe=v["timeframe"],
                    bull_argument=bull.argument,
                    bear_argument=bear.argument,
                    quant_weaknesses=(
                        "; ".join(quant.weaknesses)
                        + (f" || MEMORY: {memory_context}" if memory_context else "")
                    ),
                    rr_target=f"{_MIN_RR:.1f}",
                ),
                TaskTier.REASONING,
                "MODERATOR",
                transcript,
            )
            synthesis: ModeratorSynthesis = synthesis_raw  # type: ignore[assignment]
        except (ModelUnavailableError, GatewayHTTPError, DecodeError) as exc:
            logger.warning("debate falling back to deterministic mode: %s", exc)
            transcript.fell_back = True
            transcript.fallback_reason = f"{type(exc).__name__}: {exc}"
            return DebateResult(
                hypothesis=_deterministic_hypothesis(payload), transcript=transcript
            )

        counters = list(synthesis.counter_arguments)
        if quant.verdict == "REJECT":
            counters.append("Quant reviewer voted REJECT on statistical grounds.")

        hypothesis = CandidateHypothesis(
            symbol=payload.symbol,
            thesis=(
                f"Debate synthesis for {payload.symbol} ({payload.timeframe}): "
                f"BULL: {bull.argument} || BEAR: {bear.argument}"
            ),
            supporting_arguments=[str(a) for a in synthesis.supporting_arguments],
            counter_arguments=counters,
            timeframe=payload.timeframe,
            expected_risk_reward_ratio=max(synthesis.expected_risk_reward_ratio, _MIN_RR),
        )
        transcript.used_llm = True
        return DebateResult(hypothesis=hypothesis, transcript=transcript)

    async def _ask(
        self,
        contract: type[BaseModel],
        prompt_text: str,
        tier: str,
        role: str,
        transcript: DebateTranscript,
    ) -> BaseModel:
        parsed, response = await self._call_model(contract, prompt_text, tier)
        self._record(transcript, role, response)
        await self._emit_sink(role, response)
        return parsed


class DebateResearchAgent:
    """Drop-in replacement for ResearchAgent with the same event-handler shape."""

    def __init__(
        self,
        event_bus: BaseEventBus,
        engine: DebateEngine,
        transcript_sink: Callable[[str], Awaitable[None]] | None = None,
        debate_timeout_s: float = 35.0,
    ) -> None:
        self.event_bus = event_bus
        self.engine = engine
        self._transcript_sink = transcript_sink
        self.debate_timeout_s = debate_timeout_s

    async def on_data_acquired(self, payload: MarketDataPayload) -> None:
        try:
            result = await asyncio.wait_for(
                self.engine.debate(payload), timeout=self.debate_timeout_s
            )
        except TimeoutError:
            logger.warning(
                "debate exceeded %.0fs for %s; falling back to deterministic",
                self.debate_timeout_s,
                payload.symbol,
            )
            from communities.c2_research.debate_engine import _deterministic_hypothesis

            result = DebateResult(
                hypothesis=_deterministic_hypothesis(payload),
                transcript=DebateTranscript(
                    symbol=payload.symbol,
                    timeframe=payload.timeframe,
                    fell_back=True,
                    fallback_reason=f"debate timeout >{self.debate_timeout_s:.0f}s",
                ),
            )
        if self._transcript_sink and result.transcript.used_llm:
            await self._transcript_sink(result.transcript.model_dump_json())
        if result.hypothesis is None:
            logger.warning(
                "Debate produced no hypothesis for %s; nothing published", payload.symbol
            )
            return
        await self.event_bus.publish(EventTopic.HYPOTHESIS_GENERATED, result.hypothesis)
