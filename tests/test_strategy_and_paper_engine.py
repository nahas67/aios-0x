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
    MarketDataPayload,
    NewsSentiment,
    PriceData,
    StrategySpecification,
    TradeExecutionReceipt,
    VerificationReport,
)
from simulation.paper_engine import PaperEngine


def _payload(
    open_: float,
    high: float,
    low: float,
    close: float,
    sentiment: float,
    symbol: str = "BTC/USD",
) -> MarketDataPayload:
    """Build a deterministic MarketDataPayload for strategy tests."""
    return MarketDataPayload(
        symbol=symbol,
        timeframe="1h",
        price_data=PriceData(open=open_, high=high, low=low, close=close, volume=1500.0),
        news_sentiment=[
            NewsSentiment(title=f"Test news {symbol}", sentiment_score=sentiment, source="UnitFeed")
        ],
        is_simulated=True,
    )


def _verified_report(hypothesis: CandidateHypothesis) -> VerificationReport:
    return VerificationReport(
        hypothesis_id=hypothesis.hypothesis_id,
        confidence_score=85.0,
        verified_claims=["High volume breakout"],
        flagged_hallucinations=[],
        verification_notes="Verification successful.",
    )


def _hypothesis(symbol: str, rr: float = 2.0) -> CandidateHypothesis:
    return CandidateHypothesis(
        symbol=symbol,
        thesis="Breakout thesis",
        supporting_arguments=["Momentum"],
        counter_arguments=["Macro risk"],
        timeframe="1h",
        expected_risk_reward_ratio=rr,
    )


def test_strategy_agent_generates_buy_with_volatility_scaled_levels() -> None:
    """D3 fix: BUY derived from positive momentum + non-negative sentiment;
    stop/target scaled by realized bar range and hypothesis R:R."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        generated: list[StrategySpecification] = []

        async def handler(payload: StrategySpecification) -> None:
            generated.append(payload)

        await event_bus.subscribe(EventTopic.STRATEGY_GENERATED, handler)

        agent = StrategyAgent(event_bus=event_bus, risk_firewall=RiskFirewall(RiskConfig()))
        await agent.on_data_acquired(_payload(100.0, 102.0, 98.0, 101.0, 0.5))

        hypothesis = _hypothesis("BTC/USD", rr=2.0)

        try:
            strategy = await agent.generate_strategy(
                verification_report=_verified_report(hypothesis),
                hypothesis=hypothesis,
                daily_drawdown_pct=0.5,
            )
            await event_bus.wait_until_idle()

            assert isinstance(strategy, StrategySpecification)
            assert strategy.action == "BUY"
            assert strategy.symbol == "BTC/USD"
            assert strategy.entry_price == 101.0

            # Deterministic derivation: bar range 4% -> stop distance 2%, target 4%
            expected_stop = round(101.0 * (1.0 - 0.02), 4)
            expected_tp = round(101.0 * (1.0 + 0.04), 4)
            assert strategy.stop_loss_price == expected_stop
            assert strategy.take_profit_price == expected_tp
            assert strategy.position_size_pct == 5.0

            assert len(generated) == 1
            assert generated[0].strategy_id == strategy.strategy_id
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_strategy_agent_generates_sell_on_negative_signal() -> None:
    """D3 fix: SELL supported when momentum and sentiment are both negative."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()
        agent = StrategyAgent(event_bus=event_bus, risk_firewall=RiskFirewall(RiskConfig()))
        await agent.on_data_acquired(_payload(101.0, 103.0, 99.0, 100.0, -0.5, symbol="ETH/USD"))
        hypothesis = _hypothesis("ETH/USD", rr=2.0)

        try:
            strategy = await agent.generate_strategy(
                verification_report=_verified_report(hypothesis),
                hypothesis=hypothesis,
            )

            assert strategy is not None
            assert strategy.action == "SELL"
            assert strategy.entry_price == 100.0

            range_pct = (103.0 - 99.0) / 101.0 * 100.0
            stop_dist = min(max(range_pct * 0.5, 0.5), 4.0)
            assert strategy.stop_loss_price == pytest.approx(
                round(100.0 * (1 + stop_dist / 100.0), 4), abs=1e-6
            )
            assert strategy.take_profit_price == pytest.approx(
                round(100.0 * (1 - 2 * stop_dist / 100.0), 4), abs=1e-6
            )
            assert strategy.stop_loss_price > strategy.entry_price
            assert strategy.take_profit_price < strategy.entry_price
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_strategy_agent_no_trade_on_mixed_signal() -> None:
    """NO TRADE is a valid outcome: positive momentum but negative sentiment."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        generated: list[StrategySpecification] = []

        async def handler(payload: StrategySpecification) -> None:
            generated.append(payload)

        await event_bus.subscribe(EventTopic.STRATEGY_GENERATED, handler)

        agent = StrategyAgent(event_bus=event_bus, risk_firewall=RiskFirewall(RiskConfig()))
        await agent.on_data_acquired(_payload(100.0, 102.0, 98.0, 101.0, -0.5))
        hypothesis = _hypothesis("BTC/USD")

        try:
            strategy = await agent.generate_strategy(
                verification_report=_verified_report(hypothesis),
                hypothesis=hypothesis,
            )
            await event_bus.wait_until_idle()

            assert strategy is None
            assert len(generated) == 0
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_strategy_agent_no_trade_without_market_state() -> None:
    """D3 fix: missing market state yields NO TRADE - never an invented default price."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()
        agent = StrategyAgent(event_bus=event_bus, risk_firewall=RiskFirewall(RiskConfig()))
        hypothesis = _hypothesis("BTC/USD")

        try:
            strategy = await agent.generate_strategy(
                verification_report=_verified_report(hypothesis),
                hypothesis=hypothesis,
            )
            assert strategy is None
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_strategy_agent_rejection_by_risk_firewall() -> None:
    """Test StrategyAgent rejects strategy when Risk Firewall drawdown threshold is breached."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        generated: list[StrategySpecification] = []

        async def handler(payload: StrategySpecification) -> None:
            generated.append(payload)

        await event_bus.subscribe(EventTopic.STRATEGY_GENERATED, handler)

        agent = StrategyAgent(
            event_bus=event_bus, risk_firewall=RiskFirewall(RiskConfig(max_daily_drawdown_pct=3.0))
        )
        await agent.on_data_acquired(_payload(100.0, 102.0, 98.0, 101.0, 0.5, symbol="ETH/USD"))
        hypothesis = _hypothesis("ETH/USD", rr=2.0)

        try:
            # Trigger with daily drawdown = 3.5% (exceeds 3.0% cap)
            strategy = await agent.generate_strategy(
                verification_report=_verified_report(hypothesis),
                hypothesis=hypothesis,
                daily_drawdown_pct=3.5,
            )
            await event_bus.wait_until_idle()

            assert strategy is None
            assert len(generated) == 0
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_paper_engine_execution_debits_cash() -> None:
    """Test PaperEngine executes strategy, debits cash, and tags fill as simulated."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        executed: list[TradeExecutionReceipt] = []

        async def trade_handler(payload: TradeExecutionReceipt) -> None:
            executed.append(payload)

        await event_bus.subscribe(EventTopic.TRADE_EXECUTED, trade_handler)

        engine = PaperEngine(event_bus=event_bus, initial_balance=100000.0, slippage_pct=0.1)
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
            receipt = await engine.execute_paper_trade(strategy)
            await event_bus.wait_until_idle()

            assert isinstance(receipt, TradeExecutionReceipt)
            assert receipt.symbol == "NVDA"
            assert receipt.fill_price == 100.1  # 0.1% slippage
            assert receipt.slippage == 0.1
            assert receipt.filled_quantity > 0
            assert receipt.fees > 0

            # D5 fix: cash debited by allocated capital; position tracked; sim tagged
            assert engine.cash_balance == pytest.approx(95000.0)
            assert len(engine.open_positions) == 1
            assert receipt.is_simulated is True
            assert receipt.venue == "paper"

            assert len(executed) == 1
            assert executed[0].execution_id == receipt.execution_id
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_paper_engine_settlement_restores_cash_with_pnl() -> None:
    """D5 fix: settlement credits proceeds at a market-supplied exit price."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()
        engine = PaperEngine(event_bus=event_bus, initial_balance=100000.0, slippage_pct=0.1)
        strategy = StrategySpecification(
            hypothesis_id="hypo-settle",
            symbol="NVDA",
            action="BUY",
            entry_price=100.0,
            stop_loss_price=97.0,
            take_profit_price=106.0,
            position_size_pct=5.0,
        )

        try:
            receipt = await engine.execute_paper_trade(strategy)
            assert receipt is not None

            exit_price = 106.0
            pnl = engine.settle_position(receipt.execution_id, exit_price)

            expected_pnl = round(
                (exit_price - receipt.fill_price) * receipt.filled_quantity - receipt.fees, 2
            )
            assert pnl == expected_pnl
            assert pnl > 0
            assert engine.cash_balance == pytest.approx(100000.0 + expected_pnl, abs=0.02)
            assert len(engine.open_positions) == 0

            # Unknown id settlement returns None rather than raising
            assert engine.settle_position("missing-id", exit_price) is None
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_paper_engine_rejects_insufficient_funds() -> None:
    """D5 fix: orders exceeding available cash are rejected without publishing."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        executed: list[TradeExecutionReceipt] = []

        async def trade_handler(payload: TradeExecutionReceipt) -> None:
            executed.append(payload)

        await event_bus.subscribe(EventTopic.TRADE_EXECUTED, trade_handler)

        engine = PaperEngine(
            event_bus=event_bus, initial_balance=1.0, slippage_pct=0.1, taker_fee_pct=1.0
        )
        strategy = StrategySpecification(
            hypothesis_id="hypo-broke",
            symbol="SPY",
            action="BUY",
            entry_price=500.0,
            stop_loss_price=490.0,
            take_profit_price=520.0,
            position_size_pct=100.0,
        )

        try:
            receipt = await engine.execute_paper_trade(strategy)
            await event_bus.wait_until_idle()

            assert receipt is None
            assert len(executed) == 0
            assert engine.cash_balance == 1.0
            assert len(engine.open_positions) == 0
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_full_autonomous_trading_pipeline() -> None:
    """Test end-to-end event chain: C1 -> C2 -> C3 -> C4 -> Risk Firewall -> Paper Engine."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        executed_receipts: list[TradeExecutionReceipt] = []

        async def final_listener(payload: TradeExecutionReceipt) -> None:
            executed_receipts.append(payload)

        data_agent = DataAcquisitionAgent(fetcher=SimulatedDataFetcher(), event_bus=event_bus)
        research_agent = ResearchAgent(event_bus=event_bus)
        verification_agent = VerificationAgent(event_bus=event_bus, min_confidence_threshold=70.0)
        strategy_agent = StrategyAgent(
            event_bus=event_bus, risk_firewall=RiskFirewall(RiskConfig())
        )
        paper_engine = PaperEngine(event_bus=event_bus, initial_balance=100000.0, slippage_pct=0.05)

        await event_bus.subscribe(EventTopic.DATA_ACQUIRED, research_agent.on_data_acquired)
        await event_bus.subscribe(EventTopic.DATA_ACQUIRED, strategy_agent.on_data_acquired)
        await event_bus.subscribe(
            EventTopic.HYPOTHESIS_GENERATED, verification_agent.on_hypothesis_generated
        )
        await event_bus.subscribe(
            EventTopic.HYPOTHESIS_GENERATED, strategy_agent.on_hypothesis_generated
        )
        await event_bus.subscribe(
            EventTopic.VERIFICATION_COMPLETED, strategy_agent.on_verification_completed
        )
        await event_bus.subscribe(EventTopic.STRATEGY_GENERATED, paper_engine.on_strategy_generated)
        await event_bus.subscribe(EventTopic.TRADE_EXECUTED, final_listener)

        try:
            market_data = await data_agent.collect_and_publish("BTC/USD", "1h")
            assert market_data.symbol == "BTC/USD"

            await event_bus.wait_until_idle()

            assert len(executed_receipts) == 1
            receipt = executed_receipts[0]
            assert isinstance(receipt, TradeExecutionReceipt)
            assert receipt.symbol == "BTC/USD"
            assert receipt.fill_price > 0
            assert receipt.filled_quantity > 0
            assert receipt.is_simulated is True
            assert paper_engine.cash_balance < 100000.0
        finally:
            await event_bus.stop()

    asyncio.run(_test())
