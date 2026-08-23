"""Master unit and closed-loop integration tests for AIOS communities.

Honesty invariant (ADR-002/D1): every ObservationReport exit price originates
from market data. The pipeline never fabricates profitable outcomes.
"""

import asyncio

import pytest

from communities.c1_data.data_agent import DataAcquisitionAgent, SimulatedDataFetcher
from communities.c2_research.research_agent import ResearchAgent
from communities.c3_verification.verification_agent import VerificationAgent
from communities.c4_strategy.strategy_agent import StrategyAgent
from communities.c6_observation.observation_agent import ObservationAgent
from communities.c7_memory.memory_agent import MemoryAgent
from communities.c8_evolution.evolution_agent import EvolutionAgent, EvolutionSignal
from core.event_bus import EventTopic, InMemoryEventBus
from core.risk_firewall import RiskConfig, RiskFirewall
from schemas.contracts import ObservationReport, TradeExecutionReceipt
from simulation.paper_engine import PaperEngine


def test_observation_agent_calculates_pnl() -> None:
    """Test ObservationAgent calculates actual PnL from a supplied market exit price."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        reports: list[ObservationReport] = []

        async def handler(payload: ObservationReport) -> None:
            reports.append(payload)

        await event_bus.subscribe(EventTopic.OBSERVATION_COMPLETED, handler)

        observation_agent = ObservationAgent(event_bus=event_bus)

        receipt = TradeExecutionReceipt(
            strategy_id="strat-100",
            symbol="BTC/USD",
            fill_price=50000.0,
            filled_quantity=0.1,
            slippage=10.0,
            fees=5.0,
        )

        try:
            # Exit price of 52000.0 -> PnL = (52000 - 50000)*0.1 - 5.0 = 195.0
            report = await observation_agent.observe_trade_outcome(
                receipt=receipt, exit_price=52000.0
            )
            await event_bus.wait_until_idle()

            assert isinstance(report, ObservationReport)
            assert report.execution_id == receipt.execution_id
            assert report.actual_pnl == 195.0
            assert report.predicted_vs_actual_deviation > 0.0
            assert len(report.lessons_learned) > 0

            assert len(reports) == 1
            assert reports[0].observation_id == report.observation_id

            # D1 fix: invalid prices are rejected, never silently accepted
            with pytest.raises(ValueError):
                observation_agent.observe_trade_outcome_sync(receipt, -1.0)
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_memory_agent_persistence_and_analytics() -> None:
    """Test MemoryAgent stores records and returns a typed performance summary."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        stored_events: list[ObservationReport] = []

        async def handler(payload: ObservationReport) -> None:
            stored_events.append(payload)

        await event_bus.subscribe(EventTopic.MEMORY_STORED, handler)

        memory_agent = MemoryAgent(event_bus=event_bus)

        receipt = TradeExecutionReceipt(
            strategy_id="strat-101",
            symbol="ETH/USD",
            fill_price=3000.0,
            filled_quantity=1.0,
            slippage=1.5,
            fees=3.0,
        )
        report = ObservationReport(
            execution_id=receipt.execution_id,
            actual_pnl=150.0,
            predicted_vs_actual_deviation=0.02,
            lessons_learned=["Clean win"],
        )

        try:
            memory_agent.store_trade_receipt(receipt)
            await memory_agent.store_observation_report(report)
            await event_bus.wait_until_idle()

            assert len(memory_agent.trade_receipts) == 1
            assert len(memory_agent.observation_reports) == 1
            assert len(stored_events) == 1

            summary = memory_agent.get_performance_summary()
            assert summary.total_trades == 1
            assert summary.cumulative_pnl == 150.0
            assert summary.winning_trades == 1
            assert summary.win_rate == 100.0
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_evolution_agent_triggers_adaptation() -> None:
    """D2 fix: EvolutionAgent consumes an injected typed provider, not c7's class."""

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        signals: list[EvolutionSignal] = []

        async def handler(payload: EvolutionSignal) -> None:
            signals.append(payload)

        await event_bus.subscribe(EventTopic.EVOLUTION_TRIGGERED, handler)

        memory_agent = MemoryAgent(event_bus=event_bus)
        evolution_agent = EvolutionAgent(
            event_bus=event_bus,
            performance_provider=memory_agent.get_performance_summary,
        )

        for i in range(3):
            report = ObservationReport(
                execution_id=f"exec-{i}",
                actual_pnl=-50.0,
                predicted_vs_actual_deviation=0.05,
                lessons_learned=["Loss"],
            )
            await memory_agent.store_observation_report(report)

        try:
            signal = await evolution_agent.evaluate_and_evolve()
            await event_bus.wait_until_idle()

            assert signal.adjustment_needed is True
            assert len(signal.recommendations) >= 1
            assert signal.performance_summary.total_trades == 3
            assert signal.performance_summary.win_rate == 0.0

            assert len(signals) >= 1
            assert signals[-1].signal_id == signal.signal_id
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_master_closed_loop_8_community_pipeline() -> None:
    """Master Integration Test: full closed loop with market-driven exits only.

    C1 -> C2 -> C3 -> C4 -> Firewall -> PaperEngine -> [market price arrives] ->
    C6 observation -> C7 memory -> C8 evolution.
    """

    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        evolution_signals: list[EvolutionSignal] = []
        observations: list[ObservationReport] = []

        fetcher = SimulatedDataFetcher()
        c1_data = DataAcquisitionAgent(fetcher=fetcher, event_bus=event_bus)
        c2_research = ResearchAgent(event_bus=event_bus)
        c3_verification = VerificationAgent(event_bus=event_bus, min_confidence_threshold=70.0)
        c4_strategy = StrategyAgent(event_bus=event_bus, risk_firewall=RiskFirewall(RiskConfig()))
        paper_engine = PaperEngine(event_bus=event_bus, initial_balance=100000.0, slippage_pct=0.05)
        c6_observation = ObservationAgent(event_bus=event_bus)
        c7_memory = MemoryAgent(event_bus=event_bus)
        c8_evolution = EvolutionAgent(
            event_bus=event_bus,
            performance_provider=c7_memory.get_performance_summary,
        )

        await event_bus.subscribe(EventTopic.DATA_ACQUIRED, c2_research.on_data_acquired)
        await event_bus.subscribe(EventTopic.DATA_ACQUIRED, c4_strategy.on_data_acquired)
        await event_bus.subscribe(
            EventTopic.HYPOTHESIS_GENERATED, c3_verification.on_hypothesis_generated
        )
        await event_bus.subscribe(
            EventTopic.HYPOTHESIS_GENERATED, c4_strategy.on_hypothesis_generated
        )
        await event_bus.subscribe(
            EventTopic.VERIFICATION_COMPLETED, c4_strategy.on_verification_completed
        )
        await event_bus.subscribe(EventTopic.STRATEGY_GENERATED, paper_engine.on_strategy_generated)
        await event_bus.subscribe(EventTopic.TRADE_EXECUTED, c6_observation.on_trade_executed)
        await event_bus.subscribe(EventTopic.TRADE_EXECUTED, c7_memory.on_trade_executed)

        async def on_observation(payload: ObservationReport) -> None:
            observations.append(payload)

        async def on_signal(payload: EvolutionSignal) -> None:
            evolution_signals.append(payload)

        await event_bus.subscribe(EventTopic.OBSERVATION_COMPLETED, on_observation)
        await event_bus.subscribe(
            EventTopic.OBSERVATION_COMPLETED, c7_memory.on_observation_completed
        )
        await event_bus.subscribe(EventTopic.MEMORY_STORED, c8_evolution.on_memory_stored)
        await event_bus.subscribe(EventTopic.EVOLUTION_TRIGGERED, on_signal)

        try:
            # Trigger pipeline from C1 with deterministic simulated data
            market_data = await c1_data.collect_and_publish("BTC/USD", "1h")
            assert market_data.symbol == "BTC/USD"
            await event_bus.wait_until_idle()

            # D1 fix: no observation exists until an ACTUAL market price arrives;
            # the position remains open and nothing was fabricated.
            assert len(c7_memory.observation_reports) == 0
            assert c6_observation.open_position_count == 1

            # A real (simulated-source) market price closes the position:
            # observation AND cash settlement consume the same exit source.
            exit_candle = await fetcher.fetch_price_data("BTC/USD", "1h")
            exit_price = float(exit_candle["close"])
            await c6_observation.on_market_price_update("BTC/USD", exit_price)
            settled = paper_engine.on_market_price("BTC/USD", exit_price)
            assert len(settled) == 1
            await event_bus.wait_until_idle()

            stored_receipt = c7_memory.trade_receipts[0]
            assert stored_receipt.symbol == "BTC/USD"

            # Honest PnL computed from the actual fill and actual market exit
            expected_pnl = round(
                (exit_price - stored_receipt.fill_price) * stored_receipt.filled_quantity
                - stored_receipt.fees,
                2,
            )
            assert len(observations) == 1
            observation = observations[0]
            assert observation.actual_pnl == expected_pnl
            assert observation.execution_id == stored_receipt.execution_id

            # Deterministic sim data makes fill (entry + slippage) above the next close,
            # so realized pnl must be negative - proving no fabricated profits.
            assert expected_pnl < 0

            # Paper engine cash accounting reflects the same loss
            assert paper_engine.cash_balance == pytest.approx(100000.0 + expected_pnl, abs=0.05)

            # Evolution fired once with the typed summary
            assert len(evolution_signals) == 1
            signal = evolution_signals[0]
            assert isinstance(signal, EvolutionSignal)
            assert signal.performance_summary.total_trades == 1
            assert signal.performance_summary.cumulative_pnl == expected_pnl
        finally:
            await event_bus.stop()

    asyncio.run(_test())
