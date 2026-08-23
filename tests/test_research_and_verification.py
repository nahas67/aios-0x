"""Unit and integration tests for Research Agent (C2) and Verification Agent (C3)."""

import asyncio
import pytest

from communities.c1_data.data_agent import DataAcquisitionAgent, SimulatedDataFetcher
from communities.c2_research.research_agent import ResearchAgent
from communities.c3_verification.verification_agent import VerificationAgent
from core.event_bus import EventTopic, InMemoryEventBus
from schemas.contracts import (
    CandidateHypothesis,
    MarketDataPayload,
    PriceData,
    VerificationReport,
)


def test_research_agent_generates_and_publishes_hypothesis() -> None:
    """Test ResearchAgent analyzes MarketDataPayload, generates CandidateHypothesis, and publishes event."""
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        published_hypotheses: list[CandidateHypothesis] = []

        async def hypothesis_handler(payload: CandidateHypothesis) -> None:
            published_hypotheses.append(payload)

        await event_bus.subscribe(EventTopic.HYPOTHESIS_GENERATED, hypothesis_handler)

        research_agent = ResearchAgent(event_bus=event_bus)

        market_data = MarketDataPayload(
            symbol="BTC/USD",
            timeframe="1h",
            price_data=PriceData(
                open=44000.0,
                high=45500.0,
                low=43800.0,
                close=45200.0,
                volume=1500.0,
            ),
        )

        try:
            hypothesis = await research_agent.analyze_and_generate_hypothesis(market_data)

            await event_bus.wait_until_idle()

            assert isinstance(hypothesis, CandidateHypothesis)
            assert hypothesis.symbol == "BTC/USD"
            assert hypothesis.timeframe == "1h"
            assert len(hypothesis.supporting_arguments) > 0
            assert len(hypothesis.counter_arguments) > 0
            assert hypothesis.expected_risk_reward_ratio >= 1.5

            assert len(published_hypotheses) == 1
            assert published_hypotheses[0].hypothesis_id == hypothesis.hypothesis_id
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_verification_agent_verified_hypothesis() -> None:
    """Test VerificationAgent approves high confidence hypothesis and publishes VERIFICATION_COMPLETED."""
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        completed_reports: list[VerificationReport] = []

        async def verification_handler(payload: VerificationReport) -> None:
            completed_reports.append(payload)

        await event_bus.subscribe(EventTopic.VERIFICATION_COMPLETED, verification_handler)

        verification_agent = VerificationAgent(event_bus=event_bus, min_confidence_threshold=70.0)

        # Hypothesis with supporting args (+40), counter args (+30), R:R 2.0 (+30) -> Score 100
        valid_hypothesis = CandidateHypothesis(
            symbol="ETH/USD",
            thesis="Bullish breakout pattern verified",
            supporting_arguments=["Higher highs on volume", "MACD bullish cross"],
            counter_arguments=["Macro inflation data release pending"],
            timeframe="4h",
            expected_risk_reward_ratio=2.0,
        )

        try:
            report = await verification_agent.verify_hypothesis(valid_hypothesis)

            await event_bus.wait_until_idle()

            assert isinstance(report, VerificationReport)
            assert report.confidence_score >= 70.0
            assert report.is_verified is True
            assert report.hypothesis_id == valid_hypothesis.hypothesis_id

            assert len(completed_reports) == 1
            assert completed_reports[0].report_id == report.report_id
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_verification_agent_rejected_hypothesis() -> None:
    """Test VerificationAgent rejects low confidence hypothesis (<70) and does NOT publish event."""
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        completed_reports: list[VerificationReport] = []

        async def verification_handler(payload: VerificationReport) -> None:
            completed_reports.append(payload)

        await event_bus.subscribe(EventTopic.VERIFICATION_COMPLETED, verification_handler)

        verification_agent = VerificationAgent(event_bus=event_bus, min_confidence_threshold=70.0)

        # Hypothesis lacking counter args (0) and low R:R 1.0 (0) -> Score 40 (<70)
        flawed_hypothesis = CandidateHypothesis(
            symbol="SOL/USD",
            thesis="Unbalanced speculative impulse",
            supporting_arguments=["Recent price jump"],
            counter_arguments=[],  # Missing counter args
            timeframe="15m",
            expected_risk_reward_ratio=1.0,  # Below 1.5
        )

        try:
            report = await verification_agent.verify_hypothesis(flawed_hypothesis)

            await event_bus.wait_until_idle()

            assert isinstance(report, VerificationReport)
            assert report.confidence_score < 70.0
            assert report.is_verified is False
            assert report.hypothesis_id == flawed_hypothesis.hypothesis_id
            assert len(report.flagged_hallucinations) > 0

            # Must NOT publish to VERIFICATION_COMPLETED
            assert len(completed_reports) == 0
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_end_to_end_c1_c2_c3_pipeline() -> None:
    """Test end-to-end event chain: C1 (Data) -> C2 (Research) -> C3 (Verification)."""
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        pipeline_reports: list[VerificationReport] = []

        async def final_pipeline_handler(payload: VerificationReport) -> None:
            pipeline_reports.append(payload)

        # Initialize agents
        data_agent = DataAcquisitionAgent(
            fetcher=SimulatedDataFetcher(), event_bus=event_bus
        )
        research_agent = ResearchAgent(event_bus=event_bus)
        verification_agent = VerificationAgent(
            event_bus=event_bus, min_confidence_threshold=70.0
        )

        # Wire up event subscriptions
        await event_bus.subscribe(EventTopic.DATA_ACQUIRED, research_agent.on_data_acquired)
        await event_bus.subscribe(
            EventTopic.HYPOTHESIS_GENERATED, verification_agent.on_hypothesis_generated
        )
        await event_bus.subscribe(
            EventTopic.VERIFICATION_COMPLETED, final_pipeline_handler
        )

        try:
            # Trigger initial event flow from C1
            market_data = await data_agent.collect_and_publish("BTC/USD", "1h")
            assert market_data.symbol == "BTC/USD"

            # Wait for all background events in C1 -> C2 -> C3 pipeline to process
            await event_bus.wait_until_idle()

            # Verify that VerificationReport reached the final listener
            assert len(pipeline_reports) == 1
            final_report = pipeline_reports[0]
            assert isinstance(final_report, VerificationReport)
            assert final_report.is_verified is True
            assert final_report.confidence_score >= 70.0
        finally:
            await event_bus.stop()

    asyncio.run(_test())
