"""Master unit and closed-loop integration tests for AIOS 8-Community System."""

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
from schemas.contracts import (
    ObservationReport,
    TradeExecutionReceipt,
)
from simulation.paper_engine import PaperEngine


def test_observation_agent_calculates_pnl() -> None:
    """Test ObservationAgent calculates actual PnL, deviation score, and publishes report."""
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
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_memory_agent_persistence_and_analytics() -> None:
    """Test MemoryAgent stores receipts, observation reports, and calculates performance summary."""
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
            assert summary["total_trades"] == 1
            assert summary["cumulative_pnl"] == 150.0
            assert summary["win_rate"] == 100.0
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_evolution_agent_triggers_adaptation() -> None:
    """Test EvolutionAgent evaluates MemoryAgent summary and publishes EVOLUTION_TRIGGERED signal."""
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        evolution_signals: list[EvolutionSignal] = []

        async def handler(payload: EvolutionSignal) -> None:
            evolution_signals.append(payload)

        await event_bus.subscribe(EventTopic.EVOLUTION_TRIGGERED, handler)

        memory_agent = MemoryAgent(event_bus=event_bus)
        evolution_agent = EvolutionAgent(
            event_bus=event_bus, memory_agent=memory_agent
        )

        # Simulate 3 losing trades to trigger adaptation threshold
        for i in range(3):
            report = ObservationReport(
                execution_id=f"exec-{i}",
                actual_pnl=-50.0,
                predicted_vs_actual_deviation=0.05,
                lessons_learned=["Loss"],
            )
            await memory_agent.store_observation_report(report)

        try:
            result = await evolution_agent.evaluate_and_evolve()

            await event_bus.wait_until_idle()

            assert result["adjustment_needed"] is True
            assert len(result["recommendations"]) >= 1

            assert len(evolution_signals) >= 1
            last_signal = evolution_signals[-1]
            assert last_signal.adjustment_needed is True
        finally:
            await event_bus.stop()

    asyncio.run(_test())


def test_master_closed_loop_8_community_pipeline() -> None:
    """Master Integration Test: Verify 8-Community closed-loop event flow.

    Data (C1) -> Research (C2) -> Verification (C3) -> Strategy (C4) ->
    Risk Firewall -> Paper Engine -> Observation (C6) -> Memory (C7) -> Evolution (C8)
    """
    async def _test() -> None:
        event_bus = InMemoryEventBus()
        await event_bus.start()

        pipeline_evolution_signals: list[EvolutionSignal] = []

        async def evolution_listener(payload: EvolutionSignal) -> None:
            pipeline_evolution_signals.append(payload)

        # Instantiate all 8 Communities and Simulation Engine
        c1_data = DataAcquisitionAgent(
            fetcher=SimulatedDataFetcher(), event_bus=event_bus
        )
        c2_research = ResearchAgent(event_bus=event_bus)
        c3_verification = VerificationAgent(
            event_bus=event_bus, min_confidence_threshold=70.0
        )
        risk_firewall = RiskFirewall(RiskConfig())
        c4_strategy = StrategyAgent(
            event_bus=event_bus, risk_firewall=risk_firewall
        )
        paper_engine = PaperEngine(
            event_bus=event_bus, initial_balance=100000.0, slippage_pct=0.05
        )
        c6_observation = ObservationAgent(event_bus=event_bus)
        c7_memory = MemoryAgent(event_bus=event_bus)
        c8_evolution = EvolutionAgent(
            event_bus=event_bus, memory_agent=c7_memory
        )

        # Wire up event subscriptions across the 8-stage closed loop
        await event_bus.subscribe(
            EventTopic.DATA_ACQUIRED, c2_research.on_data_acquired
        )
        await event_bus.subscribe(
            EventTopic.DATA_ACQUIRED, c4_strategy.on_data_acquired
        )

        await event_bus.subscribe(
            EventTopic.HYPOTHESIS_GENERATED, c3_verification.on_hypothesis_generated
        )
        await event_bus.subscribe(
            EventTopic.HYPOTHESIS_GENERATED, c4_strategy.on_hypothesis_generated
        )

        await event_bus.subscribe(
            EventTopic.VERIFICATION_COMPLETED, c4_strategy.on_verification_completed
        )

        await event_bus.subscribe(
            EventTopic.STRATEGY_GENERATED, paper_engine.on_strategy_generated
        )

        await event_bus.subscribe(
            EventTopic.TRADE_EXECUTED, c6_observation.on_trade_executed
        )
        await event_bus.subscribe(
            EventTopic.TRADE_EXECUTED, c7_memory.on_trade_executed
        )

        await event_bus.subscribe(
            EventTopic.OBSERVATION_COMPLETED, c7_memory.on_observation_completed
        )

        await event_bus.subscribe(
            EventTopic.MEMORY_STORED, c8_evolution.on_memory_stored
        )

        await event_bus.subscribe(
            EventTopic.EVOLUTION_TRIGGERED, evolution_listener
        )

        try:
            # Trigger initial event from C1 Data Acquisition
            market_data = await c1_data.collect_and_publish("BTC/USD", "1h")
            assert market_data.symbol == "BTC/USD"

            # Wait for full cascade through all 8 stages
            await event_bus.wait_until_idle()

            # 1. Verify Memory Agent (C7) persisted trade receipt and observation report
            assert len(c7_memory.trade_receipts) == 1
            assert len(c7_memory.observation_reports) == 1

            receipt = c7_memory.trade_receipts[0]
            assert receipt.symbol == "BTC/USD"

            observation = c7_memory.observation_reports[0]
            assert observation.execution_id == receipt.execution_id
            assert observation.actual_pnl > 0.0

            # 2. Verify Evolution Agent (C8) received MEMORY_STORED and fired EVOLUTION_TRIGGERED
            assert len(pipeline_evolution_signals) == 1
            signal = pipeline_evolution_signals[0]
            assert isinstance(signal, EvolutionSignal)
            assert signal.performance_summary["total_trades"] == 1
            assert signal.performance_summary["cumulative_pnl"] > 0.0

        finally:
            await event_bus.stop()

    asyncio.run(_test())
