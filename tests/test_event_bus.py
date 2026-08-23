"""Unit tests for AIOS event bus in core/event_bus.py."""

import asyncio

from pydantic import BaseModel

from core.event_bus import EventTopic, InMemoryEventBus
from schemas.contracts import CandidateHypothesis, VerificationReport


def test_event_topic_enum_values() -> None:
    """Verify EventTopic enum string values match the canonical ADR-002 namespace."""
    assert EventTopic.DATA_ACQUIRED == "aios.c1.data_acquired"
    assert EventTopic.HYPOTHESIS_GENERATED == "aios.c2.hypothesis_generated"
    assert EventTopic.VERIFICATION_COMPLETED == "aios.c3.verification_completed"
    assert EventTopic.STRATEGY_GENERATED == "aios.c4.strategy_generated"
    assert EventTopic.TRADE_EXECUTED == "aios.c5.order_executed"
    assert EventTopic.OBSERVATION_COMPLETED == "aios.c6.observation_completed"
    assert EventTopic.MEMORY_STORED == "aios.c7.memory_stored"
    assert EventTopic.EVOLUTION_TRIGGERED == "aios.c8.evolution_triggered"


def test_publish_and_subscribe_hypothesis_generated() -> None:
    """Test publishing CandidateHypothesis payload to HYPOTHESIS_GENERATED topic."""

    async def _test() -> None:
        bus = InMemoryEventBus()
        await bus.start()

        received_payloads: list[BaseModel] = []

        async def hypothesis_handler(payload: BaseModel) -> None:
            received_payloads.append(payload)

        await bus.subscribe(EventTopic.HYPOTHESIS_GENERATED, hypothesis_handler)

        hypothesis = CandidateHypothesis(
            symbol="BTC/USD",
            thesis="Bullish breakout after consolidation",
            supporting_arguments=["High volume", "RSI divergence"],
            counter_arguments=["Macro resistance overhead"],
            timeframe="1h",
            expected_risk_reward_ratio=2.5,
        )

        await bus.publish(EventTopic.HYPOTHESIS_GENERATED, hypothesis)
        await bus.wait_until_idle()

        assert len(received_payloads) == 1
        assert received_payloads[0] == hypothesis
        assert isinstance(received_payloads[0], CandidateHypothesis)
        assert received_payloads[0].symbol == "BTC/USD"

        await bus.stop()

    asyncio.run(_test())


def test_multiple_subscribers_single_topic() -> None:
    """Test dispatching a single event payload to multiple registered subscribers."""

    async def _test() -> None:
        bus = InMemoryEventBus()
        await bus.start()

        handler1_payloads: list[BaseModel] = []
        handler2_payloads: list[BaseModel] = []

        async def handler_one(payload: BaseModel) -> None:
            handler1_payloads.append(payload)

        async def handler_two(payload: BaseModel) -> None:
            handler2_payloads.append(payload)

        await bus.subscribe(EventTopic.VERIFICATION_COMPLETED, handler_one)
        await bus.subscribe(EventTopic.VERIFICATION_COMPLETED, handler_two)

        report = VerificationReport(
            hypothesis_id="test-hyp-123",
            confidence_score=85.0,
            verified_claims=["Volume confirmed"],
            flagged_hallucinations=[],
            verification_notes="Verification successful.",
        )

        await bus.publish(EventTopic.VERIFICATION_COMPLETED, report)
        await bus.wait_until_idle()

        assert len(handler1_payloads) == 1
        assert len(handler2_payloads) == 1
        assert handler1_payloads[0] == report
        assert handler2_payloads[0] == report

        await bus.stop()

    asyncio.run(_test())


def test_subscriber_exception_resilience() -> None:
    """Test that an exception in one subscriber callback does not affect other subscribers or crash the bus."""

    async def _test() -> None:
        bus = InMemoryEventBus()
        await bus.start()

        successful_payloads: list[BaseModel] = []

        async def failing_handler(payload: BaseModel) -> None:
            raise ValueError("Simulated subscriber processing error!")

        async def successful_handler(payload: BaseModel) -> None:
            successful_payloads.append(payload)

        await bus.subscribe(EventTopic.HYPOTHESIS_GENERATED, failing_handler)
        await bus.subscribe(EventTopic.HYPOTHESIS_GENERATED, successful_handler)

        hypothesis = CandidateHypothesis(
            symbol="ETH/USD",
            thesis="Momentum shift",
            supporting_arguments=["Moving average cross"],
            counter_arguments=[],
            timeframe="1d",
            expected_risk_reward_ratio=1.8,
        )

        await bus.publish(EventTopic.HYPOTHESIS_GENERATED, hypothesis)
        await bus.wait_until_idle()

        # The second handler should still receive the payload despite the first handler failing
        assert len(successful_payloads) == 1
        assert successful_payloads[0] == hypothesis

        await bus.stop()

    asyncio.run(_test())


def test_publish_to_unsubscribed_topic() -> None:
    """Test publishing to a topic with no subscribers runs without error."""

    async def _test() -> None:
        bus = InMemoryEventBus()
        await bus.start()

        hypothesis = CandidateHypothesis(
            symbol="SOL/USD",
            thesis="Testing empty subscribers topic",
            supporting_arguments=[],
            counter_arguments=[],
            timeframe="15m",
            expected_risk_reward_ratio=1.0,
        )

        await bus.publish(EventTopic.DATA_ACQUIRED, hypothesis)
        await bus.wait_until_idle()

        await bus.stop()

    asyncio.run(_test())
