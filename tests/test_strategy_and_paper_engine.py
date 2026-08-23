"""Unit and full pipeline integration tests for Strategy Agent (C4) and PaperEngine."""

import asyncio
import pytest

from communities.c1_data.data_agent import DataAcquisitionAgent, SimulatedDataFetcher
from communities.c2_research.research_agent import ResearchAgent
from communities.c3_verification.verification_agent import VerificationAgent
from communities.c4_strategy.strategy_agent import StrategyAgent
from core.event_bus import EventTopic, InMemoryEventBus
from core.risk_firewall import RiskConfig, RiskFirewall
from schemas.contracts import (
    CandidateHypothesis,
    StrategySpecification,
    TradeExecutionReceipt,
    VerificationReport,
)
from simulation.paper_engine import PaperEngine


def test_strategy_agent_valid_generation() -> None:
    """Test StrategyAgent generates approved StrategySpecification and publishes STRATEGY_GENERATED."""
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        generated_strategies: list[StrategySpecification] = []

        async def strategy_handler(payload: StrategySpecification) -> None:
            generated_strategies.append(payload)

        await event_bus.subscribe(EventTopic.STRATEGY_GENERATED, strategy_handler)

        risk_firewall = RiskFirewall(RiskConfig())
        strategy_agent = StrategyAgent(event_bus=event_bus, risk_firewall=risk_firewall)

        hypothesis = CandidateHypothesis(
            symbol="BTC/USD",
            thesis="Bullish breakout thesis",
            supporting_arguments=["High volume breakout"],
            counter_arguments=["Macro resistance"],
            timeframe="1h",
            expected_risk_reward_ratio=2.0,
        )

        verification_report = VerificationReport(
            hypothesis_id=hypothesis.hypothesis_id,
            confidence_score=85.0,
            verified_claims=["High volume breakout"],
            flagged_hallucinations=[],
            verification_notes="Verification successful.",
        )

        try:
            strategy = await strategy_agent.generate_strategy(
                verification_report=verification_report,
                hypothesis=hypothesis,
                current_price=45000.0,
                daily_drawdown_pct=0.5,
            )

            await event_bus.wait_until_idle()

            assert isinstance(strategy, StrategySpecification)
            assert strategy.symbol == "BTC/USD"
            assert strategy.entry_price == 45000.0
            assert strategy.stop_loss_price == 45000.0 * 0.97
            assert strategy.take_profit_price == 45000.0 * 1.06
            assert strategy.position_size_pct == 5.0

            assert len(generated_strategies) == 1
            assert generated_strategies[0].strategy_id == strategy.strategy_id
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_strategy_agent_rejection_by_risk_firewall() -> None:
    """Test StrategyAgent rejects strategy when Risk Firewall drawdown threshold is breached."""
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        generated_strategies: list[StrategySpecification] = []

        async def strategy_handler(payload: StrategySpecification) -> None:
            generated_strategies.append(payload)

        await event_bus.subscribe(EventTopic.STRATEGY_GENERATED, strategy_handler)

        risk_firewall = RiskFirewall(RiskConfig(max_daily_drawdown_pct=3.0))
        strategy_agent = StrategyAgent(event_bus=event_bus, risk_firewall=risk_firewall)

        hypothesis = CandidateHypothesis(
            symbol="ETH/USD",
            thesis="Valid hypothesis but account in drawdown",
            supporting_arguments=["Trend momentum"],
            counter_arguments=["High volatility"],
            timeframe="1h",
            expected_risk_reward_ratio=2.0,
        )

        verification_report = VerificationReport(
            hypothesis_id=hypothesis.hypothesis_id,
            confidence_score=80.0,
            verified_claims=["Trend momentum"],
            flagged_hallucinations=[],
            verification_notes="Verified.",
        )

        try:
            # Trigger with daily drawdown = 3.5% (exceeds 3.0% cap)
            strategy = await strategy_agent.generate_strategy(
                verification_report=verification_report,
                hypothesis=hypothesis,
                current_price=3000.0,
                daily_drawdown_pct=3.5,
            )

            await event_bus.wait_until_idle()

            # Must be None when rejected by Risk Firewall
            assert strategy is None
            assert len(generated_strategies) == 0
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_paper_engine_execution() -> None:
    """Test PaperEngine executes strategy and publishes TradeExecutionReceipt."""
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        executed_trades: list[TradeExecutionReceipt] = []

        async def trade_handler(payload: TradeExecutionReceipt) -> None:
            executed_trades.append(payload)

        await event_bus.subscribe(EventTopic.TRADE_EXECUTED, trade_handler)

        paper_engine = PaperEngine(
            event_bus=event_bus, initial_balance=100000.0, slippage_pct=0.1
        )

        strategy = StrategySpecification(
            hypothesis_id="hypo-123",
            symbol="NVDA",
            action="BUY",
            entry_price=100.0,
            stop_loss_price=97.0,
            take_profit_price=106.0,
            position_size_pct=5.0,
        )

        try:
            receipt = await paper_engine.execute_paper_trade(strategy)

            await event_bus.wait_until_idle()

            assert isinstance(receipt, TradeExecutionReceipt)
            assert receipt.symbol == "NVDA"
            # Slippage is 0.1%: 100 * (1 + 0.001) = 100.1
            assert receipt.fill_price == 100.1
            assert receipt.slippage == 0.1
            assert receipt.filled_quantity > 0
            assert receipt.fees > 0

            assert len(executed_trades) == 1
            assert executed_trades[0].execution_id == receipt.execution_id
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_full_autonomous_trading_pipeline() -> None:
    """Test end-to-end event chain: C1 -> C2 -> C3 -> C4 -> Risk Firewall -> Paper Engine."""
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        executed_receipts: list[TradeExecutionReceipt] = []

        async def final_trade_listener(payload: TradeExecutionReceipt) -> None:
            executed_receipts.append(payload)

        # Initialize components
        data_agent = DataAcquisitionAgent(
            fetcher=SimulatedDataFetcher(), event_bus=event_bus
        )
        research_agent = ResearchAgent(event_bus=event_bus)
        verification_agent = VerificationAgent(
            event_bus=event_bus, min_confidence_threshold=70.0
        )
        risk_firewall = RiskFirewall(RiskConfig())
        strategy_agent = StrategyAgent(
            event_bus=event_bus, risk_firewall=risk_firewall
        )
        paper_engine = PaperEngine(
            event_bus=event_bus, initial_balance=100000.0, slippage_pct=0.05
        )

        # Subscribe handlers to build autonomous event pipeline
        await event_bus.subscribe(
            EventTopic.DATA_ACQUIRED, research_agent.on_data_acquired
        )
        await event_bus.subscribe(
            EventTopic.DATA_ACQUIRED, strategy_agent.on_data_acquired
        )

        await event_bus.subscribe(
            EventTopic.HYPOTHESIS_GENERATED, verification_agent.on_hypothesis_generated
        )
        await event_bus.subscribe(
            EventTopic.HYPOTHESIS_GENERATED, strategy_agent.on_hypothesis_generated
        )

        await event_bus.subscribe(
            EventTopic.VERIFICATION_COMPLETED, strategy_agent.on_verification_completed
        )

        await event_bus.subscribe(
            EventTopic.STRATEGY_GENERATED, paper_engine.on_strategy_generated
        )

        await event_bus.subscribe(
            EventTopic.TRADE_EXECUTED, final_trade_listener
        )

        try:
            # Trigger pipeline from Community 1
            market_data = await data_agent.collect_and_publish("BTC/USD", "1h")
            assert market_data.symbol == "BTC/USD"

            # Wait for asynchronous cascade through C1 -> C2 -> C3 -> C4 -> PaperEngine
            await event_bus.wait_until_idle()

            # Verify that the full pipeline executed and generated a trade receipt
            assert len(executed_receipts) == 1
            receipt = executed_receipts[0]
            assert isinstance(receipt, TradeExecutionReceipt)
            assert receipt.symbol == "BTC/USD"
            assert receipt.fill_price > 0
            assert receipt.filled_quantity > 0
        finally:
            await event_bus.stop()

    asyncio.run(_test())
