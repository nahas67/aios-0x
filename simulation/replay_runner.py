"""ReplayRunner: composition root for the honest historical-replay vertical slice.

Wires the full community loop over a replay dataset and enforces the Phase 1
exit criteria: market-driven bracket exits only, predictions written before
outcomes, postmortems per closed trade, hash-chained audit log, and a
timestamp-free determinism hash identical across identical runs.
"""

import hashlib
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from communities.c1_data.data_agent import BaseDataFetcher, DataAcquisitionAgent
from communities.c1_data.replay_fetcher import ReplayCursor, ReplayDataFetcher
from communities.c2_research.debate_engine import DebateEngine, DebateResearchAgent
from communities.c2_research.research_agent import ResearchAgent
from communities.c3_verification.verification_agent import VerificationAgent
from communities.c4_strategy.strategy_agent import StrategyAgent
from communities.c5_execution.adapters import PaperExecutionAdapter
from communities.c5_execution.execution import KillSwitch, OrderManager
from communities.c6_observation.observation_agent import ObservationAgent
from communities.c6_observation.postmortem_engine import PostmortemEngine
from communities.c7_memory.memory_agent import MemoryAgent
from communities.c8_evolution.evolution_agent import EvolutionAgent
from communities.c9_portfolio.portfolio import PortfolioGovernor
from communities.c10_world.macro_calendar import FileMacroCalendar
from communities.c10_world.regime_engine import RegimeEngine
from communities.c10_world.world_engines import ExpectationEngine, ScenarioEngine
from communities.c11_finance.ca_review import CAWorkflow
from communities.c11_finance.compliance import Surveillance
from communities.c11_finance.ledger import DoubleEntryLedger
from communities.c11_finance.tax import BUILTIN_RULES, LotBook, TaxEngine
from core.config import Settings
from core.data_quality import AnomalyDetector, SymbolHealthRegistry
from core.event_bus import BaseEventBus, EventTopic, InMemoryEventBus
from core.model_gateway import BaseModelGateway, ModelResponse, build_gateway
from core.model_router import ModelRouter
from core.persistence import BaseMemoryStore
from core.prompts import PromptRegistry
from core.risk_firewall import RiskConfig, RiskFirewall
from core.risk_governor import RiskGovernor, load_lockout_from_store
from kernel.receipts import Decision
from schemas.contracts import (
    CandidateHypothesis,
    Disposal,
    EmergencyStateValue,
    PortfolioAllocationPlan,
    PredictionRecord,
    ReconciliationReport,
    StrategySpecification,
    TaxComputation,
    TradeExecutionReceipt,
    VerificationReport,
)
from simulation.kernel_bridge import KernelBridge
from simulation.paper_engine import PaperEngine

if TYPE_CHECKING:
    from api.views import SystemSnapshotBuilder
    from core.challenger import ChallengeRegistry
    from core.control_plane import ControlPlane

logger = logging.getLogger(__name__)


class RunSummary(BaseModel):
    """Outcome of one replay run (timestamps excluded from determinism hash)."""

    symbols: list[str]
    total_bars: int
    trades_closed: int = 0
    wins: int = 0
    losses: int = 0
    cumulative_pnl: float = 0.0
    final_cash_balance: float = 0.0
    final_equity: float = 0.0
    max_drawdown_pct: float = 0.0
    predictions_scored: int = 0
    directional_accuracy_pct: float = 0.0
    postmortems_written: int = 0
    events_logged: int = 0
    chain_valid: bool = True
    determinism_hash: str = ""
    model_calls: int = 0
    total_model_cost_usd: float = 0.0
    research_mode_used: str = "deterministic"
    benchmark_return_pct: float = 0.0
    alpha_pct: float = 0.0
    experiment_reproducibility_hash: str = ""


def _payload_ref_id(payload: Any) -> str | None:
    for attr in (
        "hypothesis_id",
        "report_id",
        "strategy_id",
        "execution_id",
        "observation_id",
        "signal_id",
        "symbol",
    ):
        value = getattr(payload, attr, None)
        if isinstance(value, str):
            return value
    return None


class ReplayRunner:
    """Orchestrates a deterministic, honest replay across all communities."""

    def __init__(
        self,
        csv_path_by_symbol: dict[str, str | Path],
        store_path: str | Path,
        initial_balance: float = 100000.0,
        slippage_pct: float = 0.05,
        treat_as_real: bool = False,
        bus: BaseEventBus | None = None,
        store: BaseMemoryStore | None = None,
        gateway: BaseModelGateway | None = None,
        settings: Settings | None = None,
        macro_calendar_path: str | Path | None = None,
        shadow_mode: bool = False,
        use_live_news: bool = False,
    ) -> None:
        """Build the runner; call :meth:`run` to execute the replay.

        ``gateway`` injection is for tests (ScriptedModel); production builds
        from settings via :func:`build_gateway` (None => deterministic mode).
        ``macro_calendar_path`` enables C10 world-intelligence processing.
        """
        self.csv_path_by_symbol = dict(csv_path_by_symbol)
        self.symbols = sorted(self.csv_path_by_symbol)
        self.initial_balance = initial_balance
        self.slippage_pct = slippage_pct

        # ---- Constitution gate (Directive 48): refuse to operate on mismatch
        from core.constitution import enforce_at_boot

        self.constitution_hash = enforce_at_boot()

        # Library default = OFFLINE deterministic mode. Environment (.env) is
        # consulted only by explicit entry points (scripts/serve_command_center)
        # that pass settings=get_settings() — keeps tests deterministic & free.
        self.settings = settings or Settings(model_provider="none")

        self.bus = bus or InMemoryEventBus()
        if store is not None:
            self.store = store
        else:
            # Phase B: DATABASE_URL promotes persistence to PostgreSQL; the
            # default stays hermetic local SQLite.
            from core.store_factory import build_memory_store

            self.store = build_memory_store(
                store_path, database_url=self.settings.database_url
            )

        # ---- Research Plane persistence (Phase C): durable hypotheses + evidence
        from core.research_store import build_research_store
        from research.engine import HypothesisEngine

        self.research_store = build_research_store(
            store_path, database_url=self.settings.database_url
        )
        self.research_engine = HypothesisEngine(self.research_store)

        # ---- AIOS kernel (Phase A completion): every mutation below flows
        # through the authority gateway; receipts mirror into the audit log.
        self.kernel_bridge = KernelBridge(
            audit_log=self._append_kernel_event,
            research_engine=self.research_engine,
            event_bus=self.bus,
        )
        self._experiment_repro_hash = ""

        self.gateway = gateway if gateway is not None else build_gateway(self.settings)
        self.router = ModelRouter(self.gateway, self.settings)

        self.cursor = ReplayCursor()
        self.fetcher = ReplayDataFetcher(
            self.csv_path_by_symbol,
            cursor=self.cursor,
            treat_as_real=treat_as_real,
        )

        # ---- Optional live news sentiment (Finnhub) wrapped around replay prices
        if use_live_news and self.settings.finnhub_api_key:
            from communities.c1_data.data_agent import CompositeDataFetcher
            from communities.c1_data.news_providers import FinnhubNewsProvider

            provider = FinnhubNewsProvider(self.settings.finnhub_api_key)
            self.fetcher_any: BaseDataFetcher = CompositeDataFetcher(self.fetcher, provider)
            logger.warning("LIVE NEWS ENABLED (finnhub): headlines will hit the network")
        else:
            self.fetcher_any = self.fetcher

        self.c1 = DataAcquisitionAgent(fetcher=self.fetcher_any, event_bus=self.bus)

        # ---- Data-quality pipeline (Directive 9 reactions)
        self.anomaly_detector = AnomalyDetector()
        self.health = SymbolHealthRegistry()

        # ---- C10 world intelligence
        self.regime_engine = RegimeEngine(event_bus=self.bus)
        self.calendar: FileMacroCalendar | None = None
        self.expectation_engine: ExpectationEngine | None = None
        self.scenario_engine: ScenarioEngine | None = None
        if macro_calendar_path is not None:
            self.calendar = FileMacroCalendar(macro_calendar_path)
            self.expectation_engine = ExpectationEngine(event_bus=self.bus)
            self.scenario_engine = ScenarioEngine(event_bus=self.bus)

        # ---- Trading memory log (closed learning loop, created before C2)
        from core.memory_log import TradingMemoryLog

        self.memory_log = TradingMemoryLog(max_entries=200)

        # ---- C2: adversarial debate when intelligence is available, else template
        if self.settings.research_mode == "auto" and self.router.llm_available:
            self.registry = PromptRegistry()
            self.model_calls = 0
            self.total_model_cost_usd = 0.0
            debate = DebateEngine(
                router=self.router,
                registry=self.registry,
                settings=self.settings,
                model_call_sink=self._on_model_call,
                past_context_provider=self.memory_log.get_past_context,
            )
            self.c2: ResearchAgent | DebateResearchAgent = DebateResearchAgent(
                event_bus=self.bus,
                engine=debate,
                transcript_sink=self._on_transcript,
            )
            self._research_mode_used = "debate"
        else:
            self.c2 = ResearchAgent(event_bus=self.bus)
            self.model_calls = 0
            self.total_model_cost_usd = 0.0
            self._research_mode_used = "deterministic"

        self.c3 = VerificationAgent(event_bus=self.bus, min_confidence_threshold=70.0)
        self.risk_firewall = RiskFirewall(RiskConfig())
        self.c4 = StrategyAgent(
            event_bus=self.bus,
            risk_firewall=self.risk_firewall,
            portfolio_value_estimate=initial_balance,
        )
        self.paper = PaperEngine(
            event_bus=self.bus,
            initial_balance=initial_balance,
            slippage_pct=slippage_pct,
            max_open_positions_per_symbol=1,
            shadow_mode=shadow_mode,
        )
        self.c6 = ObservationAgent(event_bus=self.bus)
        self.postmortems = PostmortemEngine()
        self.c7 = MemoryAgent(event_bus=self.bus)
        self.c8 = EvolutionAgent(
            event_bus=self.bus, performance_provider=self.c7.get_performance_summary
        )

        # ---- C9 portfolio gate: nothing executes without an allocation plan
        self.governor = PortfolioGovernor(
            event_bus=self.bus,
            initial_equity=initial_balance,
            equity_provider=self._current_equity,
            exposure_by_class_provider=self._class_exposures,
        )

        # ---- C5 execution chain: plan -> order lifecycle -> venue
        self.adapter = PaperExecutionAdapter(self.paper)
        self.order_manager = OrderManager(
            event_bus=self.bus,
            adapter=self.adapter,
            quantity_provider=self._plan_quantity,
        )

        # ---- Emergency authority + kill switch
        self.risk_governor = RiskGovernor(event_bus=self.bus)
        if store is not None and load_lockout_from_store(self.store):
            from schemas.contracts import EmergencyStateValue

            self.risk_governor.state = EmergencyStateValue.EMERGENCY_HALT
            logger.warning("Boot: uncleared lockout found in audit log; trading blocked")

        # ---- Telegram notifications (fire-and-forget)
        from core.notifications import NotificationHub

        self.notifier = NotificationHub()
        if self.settings.telegram_bot_token and self.settings.telegram_chat_id:
            self.notifier.add_telegram(
                self.settings.telegram_bot_token, self.settings.telegram_chat_id
            )
            logger.warning("Telegram notifications enabled")
        self.kill_switch = KillSwitch(
            governor=self.risk_governor,
            positions_view=self._positions_view,
            flatten_callback=self._flatten_position,
            price_lookup=self._last_price_of,
        )
        self._fill_mirror: dict[str, str] = {}  # execution_id -> symbol (reconciliation)

        # ---- C11 finance back office
        self.ledger = DoubleEntryLedger(event_bus=self.bus)
        self.lot_book = LotBook()
        self.tax_engine = TaxEngine(BUILTIN_RULES["GENERIC_25"])
        self.ca_workflow = CAWorkflow()
        self.surveillance = Surveillance(event_bus=self.bus)
        self._disposals_by_execution: dict[str, list[Disposal]] = {}
        self._all_disposals: list[Disposal] = []
        self._tax_computation: TaxComputation | None = None

        # ---- Semantic memory (provenance-linked retrieval, Phase 2.0 closure)
        from core.vector_memory import InMemoryVectorMemory

        self.vector_memory = InMemoryVectorMemory()

        # ---- Agent identity roster (Directive 15/79)
        from core.agents import AgentIdentity, register_roster

        register_roster(
            self.store,
            [
                AgentIdentity(agent_id="c1-data-fabric", community="C1", role="data"),
                AgentIdentity(
                    agent_id="c2-research",
                    community="C2",
                    role="research",
                    publishes=["aios.c2.hypothesis_generated"],
                ),
                AgentIdentity(
                    agent_id="c3-verification",
                    community="C3",
                    role="verification",
                    subscribes=["aios.c2.hypothesis_generated"],
                    publishes=["aios.c3.verification_completed"],
                ),
                AgentIdentity(
                    agent_id="c4-strategy",
                    community="C4",
                    role="strategy",
                    publishes=["aios.c4.strategy_generated", "aios.c4.opportunity_ranked"],
                ),
                AgentIdentity(
                    agent_id="c5-execution",
                    community="C5",
                    role="execution",
                    publishes=["aios.c5.order_submitted", "aios.c5.order_filled"],
                ),
                AgentIdentity(
                    agent_id="c6-observation",
                    community="C6",
                    role="observation",
                    publishes=["aios.c6.observation_completed"],
                ),
                AgentIdentity(
                    agent_id="c7-memory",
                    community="C7",
                    role="memory",
                    publishes=["aios.c7.memory_stored"],
                ),
                AgentIdentity(agent_id="c8-evolution", community="C8", role="evolution"),
                AgentIdentity(
                    agent_id="c9-governor",
                    community="C9",
                    role="portfolio",
                    publishes=["aios.c9.portfolio_allocated", "aios.c9.portfolio_rejected"],
                ),
                AgentIdentity(
                    agent_id="risk-governor",
                    community="RISK",
                    role="authority",
                    publishes=["aios.risk.emergency"],
                ),
                AgentIdentity(
                    agent_id="c11-finance",
                    community="C11",
                    role="back_office",
                    publishes=["aios.c11.ledger_posted", "aios.c11.compliance_alert"],
                ),
            ],
        )

        # Decision-time caches (runner-owned; communities stay decoupled)
        self._hypotheses: dict[str, CandidateHypothesis] = {}
        self._reports: dict[str, VerificationReport] = {}
        self._strategies: dict[str, StrategySpecification] = {}
        self._receipts: dict[str, TradeExecutionReceipt] = {}
        self._pending_predictions: dict[str, PredictionRecord] = {}
        self._scored_predictions: list[PredictionRecord] = []
        self._filled_this_bar: set[str] = set()

        # Outcome collection
        self.trade_lines: list[str] = []
        self.equity_curve: list[float] = []

        self._subscriptions: list[tuple[EventTopic, Any]] = [
            (EventTopic.DATA_ACQUIRED, self._on_data_quality),
            (EventTopic.DATA_ACQUIRED, self.regime_engine.on_data_acquired),
            (EventTopic.DATA_ACQUIRED, self.c2.on_data_acquired),
            (EventTopic.DATA_ACQUIRED, self.c3.on_data_acquired),
            (EventTopic.DATA_ACQUIRED, self.c4.on_data_acquired),
            (EventTopic.DATA_ANOMALY, self.c4.on_data_anomaly),
            (EventTopic.REGIME_CHANGED, self.c4.on_regime_changed),
            (EventTopic.HYPOTHESIS_GENERATED, self.c3.on_hypothesis_generated),
            (EventTopic.HYPOTHESIS_GENERATED, self.c4.on_hypothesis_generated),
            (EventTopic.HYPOTHESIS_GENERATED, self._on_hypothesis),
            (EventTopic.VERIFICATION_COMPLETED, self.c4.on_verification_completed),
            (EventTopic.VERIFICATION_COMPLETED, self._on_verification),
            # Doc 15 gate: strategies flow through the governor, not straight to execution
            (EventTopic.STRATEGY_GENERATED, self.governor.on_strategy_generated),
            (EventTopic.PORTFOLIO_ALLOCATED, self._on_plan_execute),
            (EventTopic.TRADE_EXECUTED, self.c6.on_trade_executed),
            (EventTopic.TRADE_EXECUTED, self.c7.on_trade_executed),
            (EventTopic.TRADE_EXECUTED, self._on_receipt),
            (EventTopic.OBSERVATION_COMPLETED, self.c7.on_observation_completed),
            (EventTopic.MEMORY_STORED, self.c8.on_memory_stored),
            # ---- Kernel bridge: lifecycle tracking through the authority gateway
            (EventTopic.HYPOTHESIS_GENERATED, self.kernel_bridge.on_hypothesis),
            (EventTopic.VERIFICATION_COMPLETED, self.kernel_bridge.on_verification),
            (EventTopic.STRATEGY_GENERATED, self.kernel_bridge.on_strategy),
            (EventTopic.PORTFOLIO_ALLOCATED, self._bridge_plan_approved),
            (EventTopic.PORTFOLIO_REJECTED, self._bridge_plan_rejected),
        ]

    async def _log_event(self, payload: Any) -> None:
        # Legacy direct logger; prefer _logger_for(topic) subscriptions.
        self.store.append_event(
            type(payload).__name__, _payload_ref_id(payload), payload.model_dump(mode="json")
        )

    def _append_kernel_event(self, kind: str, ref_id: str | None, payload: dict[str, Any]) -> None:
        """Audit-log mirror for kernel decision receipts (tamper-evident trail)."""
        self.store.append_event(kind, ref_id, payload)

    def _logger_for(self, topic: EventTopic) -> Callable[[Any], Awaitable[None]]:
        """Bind the canonical topic value as the audit-log ``kind``."""

        async def _topic_logger(payload: Any) -> None:
            self.store.append_event(
                topic.value, _payload_ref_id(payload), payload.model_dump(mode="json")
            )

        return _topic_logger

    async def _on_model_call(self, role: str, response: ModelResponse) -> None:
        """Cost-intelligence sink: log every model call with its accounting."""
        self.model_calls += 1
        self.total_model_cost_usd = round(self.total_model_cost_usd + response.cost_usd, 8)
        self.store.append_event(
            "MODEL_CALL", f"{role}:{response.model}", response.model_dump(mode="json")
        )

    async def _on_transcript(self, transcript_json: str) -> None:
        self.store.append_event("TRANSCRIPT", None, {"json": transcript_json})

    def _current_equity(self) -> float:
        """Cash plus mark-to-market value of open positions (governor input)."""
        open_value = 0.0
        for p in self.paper.open_positions.values():
            try:
                close = self.fetcher.current_bar(p.receipt.symbol)["close"]
            except (IndexError, RuntimeError, KeyError):
                close = p.receipt.fill_price
            open_value += p.receipt.filled_quantity * close
        return round(self.paper.cash_balance + open_value, 2)

    def _class_exposures(self) -> dict[str, float]:
        """Open notional grouped by asset class (governor input)."""
        exposures: dict[str, float] = {}
        for p in self.paper.open_positions.values():
            cls = self.governor._classes.get(p.receipt.symbol, "OTHER")  # noqa: SLF001
            try:
                close = self.fetcher.current_bar(p.receipt.symbol)["close"]
            except (IndexError, RuntimeError, KeyError):
                close = p.receipt.fill_price
            exposures[cls] = exposures.get(cls, 0.0) + p.receipt.filled_quantity * close
        return exposures

    def _plan_quantity(self, plan: PortfolioAllocationPlan) -> float:
        """Notional sizing: equity x size% / entry price."""
        strategy = plan.strategy
        return (
            self.initial_balance
            * (plan.final_position_size_pct / 100.0)
            / max(strategy.entry_price, 1e-9)
        )

    async def _bridge_plan_approved(self, plan: PortfolioAllocationPlan) -> None:
        await self.kernel_bridge.on_plan_approved(plan)

    async def _bridge_plan_rejected(self, plan: PortfolioAllocationPlan) -> None:
        await self.kernel_bridge.on_plan_denied(
            plan.strategy.strategy_id,
            f"portfolio governor rejected plan {plan.plan_id[:8]} "
            f"({plan.strategy.action} {plan.strategy.symbol})",
        )

    async def _on_plan_execute(self, plan: PortfolioAllocationPlan) -> None:
        """Governor-approved plans enter autonomy routing here."""
        self._strategies[plan.strategy.strategy_id] = plan.strategy
        if not hasattr(self, "_control_plane"):
            self.build_control_plane()
        plane = self._control_plane

        disposition = plane.classify_plan(plan)
        if disposition == "EXECUTE":
            # Kernel authority gateway: the ONLY path from plan to order dispatch.
            auth = await self.kernel_bridge.authorize_execution(plan)
            if auth.decision is Decision.ALLOW:
                await self.order_manager.on_plan(
                    plan, locked_out=self.risk_governor.locked_out
                )
            else:
                logger.warning(
                    "AUTHORITY DENIED: order for %s held (%s)",
                    plan.strategy.symbol,
                    auth.detail,
                )
                self.store.append_event(
                    "ORDER_AUTHORITY_DENIED",
                    plan.plan_id,
                    {"reason": auth.detail, "symbol": plan.strategy.symbol},
                )
        elif disposition == "QUEUE":
            await plane.queue_for_approval(plan)
            logger.info(
                "SUPERVISED: plan %s queued for human approval (%s %s)",
                plan.plan_id[:8],
                plan.strategy.action,
                plan.strategy.symbol,
            )
        else:
            logger.info(
                "%s mode: order for %s held (plan %s)",
                plane.autonomy.value,
                plan.strategy.symbol,
                plan.plan_id[:8],
            )
            self.store.append_event(
                "PLAN_HELD",
                plan.plan_id,
                {"autonomy": plane.autonomy.value, "symbol": plan.strategy.symbol},
            )

    def _positions_view(self) -> dict[str, dict[str, str]]:
        return {
            eid: {"symbol": pos.receipt.symbol, "action": pos.action}
            for eid, pos in self.paper.open_positions.items()
        }

    def _last_price_of(self, symbol: str) -> float:
        try:
            return self.fetcher.current_bar(symbol)["close"]
        except (IndexError, RuntimeError, KeyError):
            for p in self.paper.open_positions.values():
                if p.receipt.symbol == symbol:
                    return p.receipt.fill_price
            raise

    def build_control_plane(self) -> "ControlPlane":
        """Wire the audited operator console over live components."""
        from core.challenger import ChallengeRegistry
        from core.control_plane import ControlPlane

        if not hasattr(self, "_challenge_registry"):
            self._challenge_registry = ChallengeRegistry(self.store)
        if not hasattr(self, "_control_plane"):
            plane = ControlPlane(
                store=self.store,
                event_bus=self.bus,
                risk_governor=self.risk_governor,
                strategy_agent=self.c4,
                order_manager=self.order_manager,
                governor=self.governor,
                paper_engine=self.paper,
                challenge_registry=self._challenge_registry,
                settings_ref=self.settings,
                price_lookup=self._last_price_of,
                flatten_callback=self._flatten_position,
                positions_view=self._positions_view,
            )
            # SUPERVISED approvals must reach the real execution path:
            plane._execute_bridge(  # noqa: SLF001 - composition-root wiring
                lambda plan: self.order_manager.on_plan(
                    plan, locked_out=self.risk_governor.locked_out
                )
            )
            self._control_plane = plane
        return self._control_plane

    def build_challenge_registry(self) -> "ChallengeRegistry":
        if not hasattr(self, "_challenge_registry"):
            from core.challenger import ChallengeRegistry

            self._challenge_registry = ChallengeRegistry(self.store)
        return self._challenge_registry

    def build_snapshot_builder(self) -> "SystemSnapshotBuilder":
        """Expose read-only command-center views over this run."""
        from api.views import SystemSnapshotBuilder

        return SystemSnapshotBuilder(
            store=self.store,
            ledger=self.ledger,
            governor=self.governor,
            risk_governor=self.risk_governor,
            paper_engine=self.paper,
            lot_book=self.lot_book,
            settings=self.settings,
            control_plane=self.build_control_plane(),
            order_manager=self.order_manager,
            regime_engine=self.regime_engine,
            equity_curve=self.equity_curve,
            benchmark_curve=getattr(self, "benchmark_curve", []),
            research_engine=self.research_engine,
        )

    def serve(self, port: int = 8787) -> Any:
        """Start the command-center HTTP server on a daemon thread."""
        from api.server import CommandCenterServer

        server = CommandCenterServer(
            self.build_snapshot_builder(), self.build_control_plane(), port=port
        )
        server.start()
        logger.warning("Command center serving on http://127.0.0.1:%s", server.port)
        return server

    async def _flatten_position(self, execution_id: str, exit_price: float) -> None:
        position = self.paper.open_positions.get(execution_id)
        if position is None:
            return
        await self._settle(position.receipt, exit_price, "KILL_SWITCH")

    async def _reconcile(self) -> ReconciliationReport:
        """Adapter snapshot vs internal fill mirror; mismatch = execution failure."""
        venue_positions = self.adapter.positions_snapshot()
        mirror_symbols = set(self._fill_mirror.values())
        mismatches: list[str] = []
        for symbol in sorted(set(venue_positions) | mirror_symbols):
            venue_qty = venue_positions.get(symbol)
            internal_open = any(
                p.receipt.symbol == symbol for p in self.paper.open_positions.values()
            )
            if venue_qty is not None and not internal_open and venue_qty > 0:
                mismatches.append(f"{symbol}: venue reports {venue_qty} qty; internal none")
            if venue_qty is None and internal_open:
                # Paper adapter mirrors engine by construction; divergence = bug/tamper.
                mismatches.append(f"{symbol}: internal open position missing at venue")
        report = ReconciliationReport(
            checked_symbols=len(set(venue_positions) | mirror_symbols),
            mismatches=mismatches,
        )
        if not report.ok:
            await self.bus.publish(EventTopic.RECONCILIATION_FAILED, report)
            await self.risk_governor.observe_reconciliation(report)
            await self.kill_switch.trigger("reconciliation failed", triggered_by="reconciler")
        return report

    async def _on_data_quality(self, payload: Any) -> None:
        """Run anomaly detection + health tracking for every data arrival.

        Subscribed BEFORE research/strategy handlers so freeze reactions apply
        within the same bar cascade.
        """
        self.health.apply_payload(payload)
        for alert in self.anomaly_detector.ingest(payload):
            self.health.apply_alert(alert)
            await self.bus.publish(EventTopic.DATA_ANOMALY, alert)

    async def _process_due_events(self) -> None:
        """Publish pre-event scenarios and post-release expectation snapshots."""
        if self.calendar is None or self.expectation_engine is None:
            return
        current_ts = self.fetcher.current_timestamp()
        for event in self.calendar.due_events(current_ts):
            if event.actual is None and self.scenario_engine is not None:
                await self.scenario_engine.on_event(event)
            elif event.actual is not None:
                if self.scenario_engine is not None:
                    await self.scenario_engine.on_event(event)
                await self.expectation_engine.on_event(event)

    async def _on_hypothesis(self, hypothesis: CandidateHypothesis) -> None:
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis

    async def _on_verification(self, report: VerificationReport) -> None:
        self._reports[report.hypothesis_id] = report

    async def _on_strategy_generated(self, strategy: StrategySpecification) -> None:
        """Legacy cache path (direct-wiring tests); production uses _on_plan."""
        self._strategies[strategy.strategy_id] = strategy

    async def _on_plan(self, plan: PortfolioAllocationPlan) -> None:
        """Cache allocated strategies for settlement attribution."""
        if plan.approved:
            self._strategies[plan.strategy.strategy_id] = plan.strategy

    async def _on_receipt(self, receipt: TradeExecutionReceipt) -> None:
        """Register a real fill and open its prediction-ledger entry.

        Predictions are written for executed trades only (before any outcome),
        because strategies blocked by portfolio limits were never decisions
        taken - scoring them would corrupt calibration statistics.
        """
        self._receipts[receipt.execution_id] = receipt
        self._fill_mirror[receipt.execution_id] = receipt.symbol
        self._filled_this_bar.add(receipt.execution_id)
        await self.kernel_bridge.on_receipt(receipt)

        # C11 hooks: double-entry books + tax lot opening + surveillance
        await self.ledger.post_fill_open(
            symbol=receipt.symbol,
            fill_price=receipt.fill_price,
            quantity=receipt.filled_quantity,
            fees=receipt.fees,
            execution_id=receipt.execution_id,
        )
        self.lot_book.open_from_fill(receipt, opened_at=self.fetcher.current_timestamp())
        await self.surveillance.check_fill(receipt, action_hint="BUY")

        # Memory log: store the decision (Phase A pending)
        strategy = self._strategies.get(receipt.strategy_id)
        hypothesis = self._hypotheses.get(strategy.hypothesis_id) if strategy else None
        if strategy and hypothesis:
            self.memory_log.store_decision(
                symbol=receipt.symbol,
                trade_date=self.fetcher.current_timestamp().strftime("%Y-%m-%d"),
                action=strategy.action,
                decision=hypothesis.thesis[:500],
            )

        if receipt.strategy_id in self._pending_predictions:
            return
        strategy = self._strategies.get(receipt.strategy_id)
        hypothesis_id = strategy.hypothesis_id if strategy else ""
        hypothesis = self._hypotheses.get(hypothesis_id)
        report = self._reports.get(hypothesis_id)
        direction: str = strategy.action if strategy else "BUY"
        prediction = PredictionRecord(
            hypothesis_id=hypothesis_id or "unknown",
            strategy_id=receipt.strategy_id,
            symbol=receipt.symbol,
            direction="BUY" if direction == "BUY" else "SELL",
            entry_reference_price=strategy.entry_price if strategy else receipt.fill_price,
            target_price=strategy.take_profit_price if strategy else receipt.fill_price * 1.02,
            stop_price=strategy.stop_loss_price if strategy else receipt.fill_price * 0.99,
            horizon_timeframe=hypothesis.timeframe if hypothesis else "1d",
            confidence_score=report.confidence_score if report else 70.0,
            expected_risk_reward_ratio=(
                hypothesis.expected_risk_reward_ratio if hypothesis else 2.0
            ),
            decision_bar_timestamp=self.fetcher.current_timestamp(),
            is_simulated=True,
        )
        self._pending_predictions[receipt.strategy_id] = prediction
        self.store.save_prediction(prediction)

    def _evaluate_bracket_exits(self) -> list[tuple[TradeExecutionReceipt, float, str]]:
        """Check open positions against the CURRENT bar; conservative stop-first rule."""
        exits: list[tuple[TradeExecutionReceipt, float, str]] = []
        slip_frac = self.slippage_pct / 100.0
        for execution_id, position in list(self.paper.open_positions.items()):
            if execution_id in self._filled_this_bar:
                continue  # never exit on the entry bar itself
            bar = self.fetcher.current_bar(position.receipt.symbol)
            low, high = bar["low"], bar["high"]
            r = position.receipt
            exit_price: float
            reason: str
            if position.action == "BUY":
                if low <= position.stop_loss_price:
                    exit_price, reason = (
                        round(position.stop_loss_price * (1 - slip_frac), 4),
                        "STOP_HIT",
                    )
                elif high >= position.take_profit_price:
                    exit_price, reason = position.take_profit_price, "TARGET_HIT"
                else:
                    continue
            else:
                if high >= position.stop_loss_price:
                    exit_price, reason = (
                        round(position.stop_loss_price * (1 + slip_frac), 4),
                        "STOP_HIT",
                    )
                elif low <= position.take_profit_price:
                    exit_price, reason = position.take_profit_price, "TARGET_HIT"
                else:
                    continue
            exits.append((r, exit_price, reason))
        return exits

    async def _settle(self, receipt: TradeExecutionReceipt, exit_price: float, reason: str) -> None:
        pnl_opt = self.paper.settle_position(receipt.execution_id, exit_price)
        if pnl_opt is None:
            logger.warning("Settlement skipped for unknown execution %s", receipt.execution_id)
            return

        # C11 hooks: FIFO lot consumption + realized-pnl ledger legs
        disposals: list[Disposal] = []
        try:
            disposals = self.lot_book.consume(
                receipt.symbol,
                receipt.filled_quantity,
                exit_price,
                disposed_at=self.fetcher.current_timestamp(),
                ref_execution_id_exit=receipt.execution_id,
            )
            self._disposals_by_execution[receipt.execution_id] = disposals
            await self.ledger.post_exit_close(
                symbol=receipt.symbol,
                basis_released_minor=sum(d.basis_minor for d in disposals),
                proceeds_minor=sum(d.proceeds_minor for d in disposals),
                realized_pnl_minor=sum(d.gain_minor for d in disposals),
                execution_id=receipt.execution_id,
            )
        except ValueError as exc:
            logger.error("lot consumption failed for %s: %s", receipt.execution_id, exc)

        # Memory log: resolve pending decision with outcome (Phase B)
        if pnl_opt is not None:
            raw_ret = pnl_opt / (self.initial_balance * 0.05) * 100  # approx % on position
            await self.memory_log.update_with_outcome(
                symbol=receipt.symbol,
                trade_date=self.fetcher.current_timestamp().strftime("%Y-%m-%d"),
                raw_return=round(raw_ret, 2),
                alpha_return=round(raw_ret, 2),  # alpha vs self until benchmark wired
                holding_days=1,
            )

        strategy = self._strategies.get(receipt.strategy_id)
        hypothesis = self._hypotheses.get(strategy.hypothesis_id) if strategy else None
        prediction = self._pending_predictions.pop(receipt.strategy_id, None)
        postmortem = None

        await self.c6.observe_trade_outcome(
            receipt,
            exit_price,
            exit_reason=reason,
            side=strategy.action if strategy else "BUY",
        )
        await self.bus.wait_until_idle()  # ensure C7 has persisted the report

        observation = next(
            (
                r
                for r in reversed(self.c7.observation_reports)
                if r.execution_id == receipt.execution_id
            ),
            None,
        )

        if prediction is not None:
            direction_correct = bool(
                (prediction.direction == "BUY" and exit_price > receipt.fill_price)
                or (prediction.direction == "SELL" and exit_price < receipt.fill_price)
            )
        elif observation is not None and observation.direction_correct is not None:
            direction_correct = observation.direction_correct
        else:
            direction_correct = False

        if strategy and hypothesis and observation:
            self.store.save_observation(observation)
            # Semantic memory: lessons retrievable by future research cycles
            try:
                self.vector_memory.upsert(
                    "postmortem_lessons",
                    f"{receipt.execution_id}:{strategy.symbol}",
                    (
                        f"{strategy.symbol} {strategy.action} exit {reason} pnl "
                        f"{observation.actual_pnl:+.2f}: " + " | ".join(observation.lessons_learned)
                    ),
                    {
                        "execution_id": receipt.execution_id,
                        "family": strategy.family,
                        "pnl": observation.actual_pnl,
                        "decision_ts": prediction.decision_bar_timestamp.isoformat()
                        if prediction
                        else None,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - memory must not break trading loop
                logger.warning("vector upsert skipped: %s", exc)

            postmortem = self.postmortems.build(
                hypothesis=hypothesis,
                strategy=strategy,
                receipt=receipt,
                observation=observation,
                exit_price=exit_price,
                exit_reason=reason,
                prediction_id=prediction.prediction_id if prediction else None,
            )
            self.store.save_postmortem(postmortem)

        # Kernel learning loop: EVALUATED + hypothesis verdict + postmortem lineage
        await self.kernel_bridge.on_settled(
            receipt,
            exit_reason=reason,
            realized_pnl=pnl_opt,
            direction_correct=direction_correct,
            postmortem=postmortem,
        )

        if prediction is not None:
            scored = prediction.score(
                exit_price=exit_price,
                exit_reason=reason,  # type: ignore[arg-type]
                realized_pnl=pnl_opt,
                direction_correct=direction_correct,
            )
            self.store.save_prediction(scored)
            self._scored_predictions.append(scored)
            self.trade_lines.append(
                f"{strategy.symbol if strategy else receipt.symbol}"
                f"|{prediction.decision_bar_timestamp.isoformat()}"
                f"|{prediction.direction}|{receipt.fill_price}|{reason}|{exit_price}|{round(pnl_opt, 2)}"
            )

    def _finalize_finance(self) -> None:
        """C11 closure: aggregate all disposals -> cited tax computation -> CA item.

        The computation is ADVISORY and lands in DRAFT/PREPARED review state;
        filing remains impossible until a licensed professional approves it.
        """
        if not self._all_disposals:
            self._all_disposals = [
                d
                for exec_disposals in self._disposals_by_execution.values()
                for d in exec_disposals
            ]
        if not self._all_disposals:
            return

        computation: TaxComputation = self.tax_engine.compute(self._all_disposals)
        self._tax_computation = computation
        self.store.append_event(
            "TAX_COMPUTATION",
            computation.computation_id,
            computation.model_dump(mode="json"),
        )

        item = self.ca_workflow.create(
            subject_kind="tax_computation", subject_ref=computation.computation_id
        )
        self.ca_workflow.prepare(item.item_id, prepared_by="c11-back-office")
        self.store.append_event(
            "REVIEW_ITEM",
            item.item_id,
            {
                "subject_ref": computation.computation_id,
                "state": item.state.value,
                "prepared_by": item.prepared_by,
            },
        )
        logger.info(
            "Finance finalized: tax %s (%s) queued for CA review as %s",
            computation.computation_id,
            computation.rule_id,
            item.item_id,
        )

    async def run(self) -> RunSummary:
        """Execute the replay to exhaustion and return an honest summary."""
        await self.bus.start()
        for topic, handler in self._subscriptions:
            await self.bus.subscribe(topic, handler)
        for topic in EventTopic:
            await self.bus.subscribe(topic, self._logger_for(topic))

        # Kernel data plane: versioned dataset + feature, then the pinned
        # ExperimentRun (dataset version + seed + config + reproducibility hash).
        await self.kernel_bridge.register_replay_dataset(self.csv_path_by_symbol)
        self._experiment_repro_hash = await self.kernel_bridge.start_experiment(
            symbols=self.symbols,
            configuration={
                "initial_balance": self.initial_balance,
                "slippage_pct": self.slippage_pct,
                "research_mode": self.settings.research_mode,
                "shadow_mode": self.paper.shadow_mode,
            },
        )

        total_bars = min(self.fetcher.bar_count(s) for s in self.symbols)
        benchmark_initial: dict[str, float] = {}
        self.benchmark_curve: list[float] = []
        try:
            for _bar_idx in range(total_bars):
                self.cursor.advance()
                self._filled_this_bar.clear()
                exhausted = False
                for symbol in self.symbols:
                    try:
                        await self.c1.collect_and_publish(symbol, "1d")
                    except IndexError:
                        exhausted = True
                    except Exception as exc:  # noqa: BLE001 - venue/feed outage drill
                        logger.error("feed failure for %s: %s", symbol, exc)
                        await self.risk_governor.escalate(
                            EmergencyStateValue.DATA_FAILURE,
                            f"ingestion outage on {symbol}: {type(exc).__name__}",
                            triggered_by="data_fabric",
                        )
                await self.bus.wait_until_idle()

                # Benchmark: equal-weight buy-and-hold from bar 0 closes
                benchmark_value = 0.0
                for symbol in self.symbols:
                    close = float(self.fetcher.current_bar(symbol)["close"])
                    if symbol not in benchmark_initial:
                        benchmark_initial[symbol] = close
                    if benchmark_initial[symbol] > 0:
                        benchmark_value += (
                            self.initial_balance
                            / len(self.symbols)
                            * (close / benchmark_initial[symbol])
                        )
                self.benchmark_curve.append(round(benchmark_value, 2))

                await self._process_due_events()
                await self.bus.wait_until_idle()

                for receipt, exit_price, reason in self._evaluate_bracket_exits():
                    await self._settle(receipt, exit_price, reason)

                # Emergency supervision chain (per bar)
                dd = self.governor.current_drawdown_pct()
                await self.risk_governor.observe_drawdown(dd, halt_threshold_pct=3.0)
                if self.risk_governor.locked_out and self.paper.open_positions:
                    await self.kill_switch.trigger(
                        f"drawdown {dd:.2f}% halt", triggered_by="portfolio_governor"
                    )
                    if self.notifier.has_channels:
                        await self.notifier.notify(
                            f"KILL SWITCH: drawdown {dd:.2f}% hit halt threshold. "
                            f"All positions flattened. Trading locked.",
                            severity="CRITICAL",
                        )
                await self._reconcile()

                open_value = 0.0
                for p in self.paper.open_positions.values():
                    close = self.fetcher.current_bar(p.receipt.symbol)["close"]
                    open_value += p.receipt.filled_quantity * close
                self.equity_curve.append(round(self.paper.cash_balance + open_value, 2))

                if exhausted:
                    break

            # Horizon end: force-close remaining positions at last close
            for position in list(self.paper.open_positions.values()):
                bar = self.fetcher.current_bar(position.receipt.symbol)
                await self._settle(position.receipt, bar["close"], "HORIZON_END")

            # Final equity sample after all settlements (all cash, no open positions)
            self.equity_curve.append(round(self.paper.cash_balance, 2))

            self._finalize_finance()

            # Complete the kernel experiment BEFORE the bus stops so the
            # ExperimentCompleted platform event reaches the audit logger.
            summary = self._summarize(total_bars)
            await self.kernel_bridge.complete_experiment(
                {
                    "trades_closed": summary.trades_closed,
                    "cumulative_pnl": summary.cumulative_pnl,
                    "max_drawdown_pct": summary.max_drawdown_pct,
                    "directional_accuracy_pct": summary.directional_accuracy_pct,
                    "alpha_pct": summary.alpha_pct,
                    "determinism_hash": summary.determinism_hash,
                }
            )
            await self.bus.wait_until_idle()
        finally:
            await self.bus.stop()

        summary.experiment_reproducibility_hash = self._experiment_repro_hash
        return summary

    def _summarize(self, total_bars: int) -> RunSummary:
        perf = self.c7.get_performance_summary()
        scored = self._scored_predictions
        correct = sum(1 for p in scored if p.direction_correct)
        equity = self.equity_curve or [self.initial_balance]
        peak = equity[0]
        max_dd = 0.0
        for value in equity:
            peak = max(peak, value)
            if peak > 0:
                max_dd = max(max_dd, (peak - value) / peak * 100.0)
        digest = hashlib.sha256("|".join(self.trade_lines).encode()).hexdigest()
        chain_ok, _ = self.store.verify_chain()
        counts = self.store.counts()

        bench_return = 0.0
        if self.benchmark_curve and self.benchmark_curve[0] > 0:
            bench_return = round(
                (self.benchmark_curve[-1] - self.benchmark_curve[0])
                / self.benchmark_curve[0]
                * 100.0,
                2,
            )
        our_return = 0.0
        if equity and equity[0] > 0:
            our_return = round((equity[-1] - equity[0]) / equity[0] * 100.0, 2)

        return RunSummary(
            symbols=self.symbols,
            total_bars=total_bars,
            trades_closed=int(perf.total_trades),
            wins=int(perf.winning_trades),
            losses=int(perf.total_trades - perf.winning_trades),
            cumulative_pnl=float(perf.cumulative_pnl),
            final_cash_balance=self.paper.cash_balance,
            final_equity=equity[-1],
            max_drawdown_pct=round(max_dd, 2),
            predictions_scored=len(scored),
            directional_accuracy_pct=(round(correct / len(scored) * 100.0, 2) if scored else 0.0),
            postmortems_written=counts["postmortems"],
            events_logged=counts["event_log"],
            chain_valid=chain_ok,
            determinism_hash=digest,
            model_calls=self.model_calls,
            total_model_cost_usd=self.total_model_cost_usd,
            research_mode_used=self._research_mode_used,
            benchmark_return_pct=bench_return,
            alpha_pct=round(our_return - bench_return, 2),
        )
