"""ReplayRunner: composition root for the honest historical-replay vertical slice.

Wires the full community loop over a replay dataset and enforces the Phase 1
exit criteria: market-driven bracket exits only, predictions written before
outcomes, postmortems per closed trade, hash-chained audit log, and a
timestamp-free determinism hash identical across identical runs.
"""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
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
from communities.c5_execution.broker_reconciliation import snapshot_from_rows
from communities.c5_execution.execution import KillSwitch, OrderManager
from communities.c5_execution.reconciliation import (
    ReconciliationEngine,
    ReconciliationResult,
)
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
from core.financial_kernel import (
    BaseFinancialStore,
    Fill,
    FinancialStoreError,
    ReconciliationMode,
)
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
    OrderSide,
    PortfolioAllocationPlan,
    PredictionRecord,
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
    from core.settings_plane import SettingsPlane

logger = logging.getLogger(__name__)

#: Adapter version recorded on every per-bar reconciliation run, so a finding can
#: always be traced to the code that produced the venue's answer.
PAPER_RECONCILIATION_ADAPTER = "paper-positions-only-1.0"

#: Notional ceiling the execution Guardian clamps to in the paper tier. A paper
#: tier has no capital at risk, so this is not a safety control -- it is a
#: deliberate stand-in for the real firewall, so that a clamp reached in replay
#: is the clamp that will run in testnet. A replay path that never exercises
#: governance cannot demonstrate that governance works.
_REPLAY_MAX_NOTIONAL = 5000.0

#: Fallback signing secret for the replay tier only. Per-deployment deployments
#: must set AIOS_GOVERNANCE_SECRET; this constant exists so `python -m aios
#: replay` works from a clean checkout without pretending the paper tier is
#: authenticated. It is deliberately NOT used by the live or testnet adapters.
_REPLAY_GOVERNANCE_SECRET = b"aios-replay-tier-not-a-production-key"


def _replay_governance_secret() -> bytes:
    """Signing key for the replay tier: deployment secret, else the paper default."""
    from kernel.tool_governance import GovernanceError, guardian_secret_from_env

    try:
        return guardian_secret_from_env()
    except GovernanceError:
        logger.warning(
            "AIOS_GOVERNANCE_SECRET unset; using the replay-tier paper key. A signature "
            "from this key authenticates nothing, so it is confined to the paper tier."
        )
        return _REPLAY_GOVERNANCE_SECRET

# ---- Zero-trust publishing map (§24): actor -> topics it may publish.
# Everything else (DATA_ANOMALY, RECONCILIATION_FAILED, aios.platform.*) is
# published by the composition root / kernel bridge on the unscoped bus.
_COMPONENT_BUS_SCOPES: dict[str, frozenset[EventTopic]] = {
    "c1-data-fabric": frozenset({EventTopic.DATA_ACQUIRED}),
    "c2-research": frozenset({EventTopic.HYPOTHESIS_GENERATED}),
    "c3-verification": frozenset({EventTopic.VERIFICATION_COMPLETED}),
    "c4-strategy": frozenset(
        {EventTopic.STRATEGY_GENERATED, EventTopic.OPPORTUNITY_RANKED}
    ),
    "c5-execution": frozenset(
        {
            EventTopic.ORDER_SUBMITTED,
            EventTopic.ORDER_FILLED,
            EventTopic.TRADE_EXECUTED,
        }
    ),
    "c6-observation": frozenset({EventTopic.OBSERVATION_COMPLETED}),
    "c7-memory": frozenset({EventTopic.MEMORY_STORED}),
    "c8-evolution": frozenset({EventTopic.EVOLUTION_TRIGGERED}),
    "c9-governor": frozenset(
        {
            EventTopic.OPPORTUNITY_RANKED,
            EventTopic.PORTFOLIO_ALLOCATED,
            EventTopic.PORTFOLIO_REJECTED,
        }
    ),
    "c10-world": frozenset(
        {
            EventTopic.REGIME_CHANGED,
            EventTopic.EXPECTATION_UPDATED,
            EventTopic.SCENARIOS_PUBLISHED,
        }
    ),
    "c11-finance": frozenset(
        {EventTopic.LEDGER_POSTED, EventTopic.COMPLIANCE_ALERT}
    ),
    "risk-governor": frozenset({EventTopic.RISK_EMERGENCY}),
}


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
    durable_orders: int = 0
    durable_fills: int = 0
    durable_open_orders: int = 0
    financial_invariants_ok: bool = True
    ibor_rebuild_ok: bool = True
    outbox_backlog: int = 0
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
        csv_path_by_symbol: Mapping[str, str | Path],
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
        financial_store: BaseFinancialStore | None = None,
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
        # Retained so serve-time builders can derive sibling state files
        # (settings plane) from the same base path without new arguments.
        self.store_path = Path(store_path)

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
        from research.auto_research import AutoResearchEngine
        from research.engine import HypothesisEngine

        self.research_store = build_research_store(
            store_path, database_url=self.settings.database_url
        )
        self.research_engine = HypothesisEngine(self.research_store)
        self.auto_research = AutoResearchEngine(self.research_store)

        # ---- AIOS kernel (Phase A completion): every mutation below flows
        # through the authority gateway; receipts mirror into the audit log.
        self.kernel_bridge = KernelBridge(
            audit_log=self._append_kernel_event,
            research_engine=self.research_engine,
            event_bus=self.bus,
        )
        self._scoped_buses: list[Any] = []
        self._experiment_repro_hash = ""

        self.gateway = gateway if gateway is not None else build_gateway(self.settings)
        self.router = ModelRouter(self.gateway, self.settings)

        self.cursor = ReplayCursor()
        self.fetcher = ReplayDataFetcher(
            self.csv_path_by_symbol,
            cursor=self.cursor,
            treat_as_real=treat_as_real,
        )

        # ---- Optional live news sentiment wrapped around replay prices
        if use_live_news and self.settings.finnhub_api_key:
            from communities.c1_data.data_agent import CompositeDataFetcher
            from communities.c1_data.news_providers import build_news_chain

            chain = build_news_chain(self.settings)
            assert chain is not None  # finnhub key present per condition
            self.fetcher_any: BaseDataFetcher = CompositeDataFetcher(self.fetcher, chain)
            logger.warning(
                "LIVE NEWS ENABLED via %s", type(chain).__name__
            )
        else:
            self.fetcher_any = self.fetcher

        self.c1 = DataAcquisitionAgent(fetcher=self.fetcher_any, event_bus=self._scoped("c1-data-fabric"))

        # ---- Data-quality pipeline (Directive 9 reactions)
        self.anomaly_detector = AnomalyDetector()
        self.health = SymbolHealthRegistry()

        # ---- C10 world intelligence
        self.regime_engine = RegimeEngine(event_bus=self._scoped("c10-world"))
        self.calendar: FileMacroCalendar | None = None
        self.expectation_engine: ExpectationEngine | None = None
        self.scenario_engine: ScenarioEngine | None = None
        if macro_calendar_path is not None:
            self.calendar = FileMacroCalendar(macro_calendar_path)
            self.expectation_engine = ExpectationEngine(event_bus=self._scoped("c10-world"))
            self.scenario_engine = ScenarioEngine(event_bus=self._scoped("c10-world"))

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
                event_bus=self._scoped("c2-research"),
                engine=debate,
                transcript_sink=self._on_transcript,
            )
            self._research_mode_used = "debate"
        else:
            self.c2 = ResearchAgent(event_bus=self._scoped("c2-research"))
            self.model_calls = 0
            self.total_model_cost_usd = 0.0
            self._research_mode_used = "deterministic"

        self.c3 = VerificationAgent(event_bus=self._scoped("c3-verification"), min_confidence_threshold=70.0)
        self.risk_firewall = RiskFirewall(RiskConfig())
        self.c4 = StrategyAgent(
            event_bus=self._scoped("c4-strategy"),
            risk_firewall=self.risk_firewall,
            portfolio_value_estimate=initial_balance,
        )
        self.paper = PaperEngine(
            event_bus=self._scoped("c5-execution"),
            initial_balance=initial_balance,
            slippage_pct=slippage_pct,
            max_open_positions_per_symbol=1,
            shadow_mode=shadow_mode,
        )
        self.c6 = ObservationAgent(event_bus=self._scoped("c6-observation"))
        self.postmortems = PostmortemEngine()
        self.c7 = MemoryAgent(event_bus=self._scoped("c7-memory"))
        self.c8 = EvolutionAgent(
            event_bus=self._scoped("c8-evolution"), performance_provider=self.c7.get_performance_summary
        )

        # ---- C9 portfolio gate: nothing executes without an allocation plan
        self.governor = PortfolioGovernor(
            event_bus=self._scoped("c9-governor"),
            initial_equity=initial_balance,
            equity_provider=self._current_equity,
            exposure_by_class_provider=self._class_exposures,
        )

        # ---- Deterministic financial state plane (V1-A): durable OMS + IBOR.
        # Orders are written ahead of the venue call, fills are applied exactly
        # once, and the book is rebuildable from the fill ledger. Bus/audit
        # semantics are unchanged: no extra topics are published here, the
        # outbox is drained by the dedicated publisher process.
        from communities.c5_execution.oms import DurableOrderManager
        from core.financial_kernel import build_financial_store
        from core.ibor import InvestmentBookOfRecord
        from core.safety_plane import SafetyPlane

        self.financial_store = financial_store or build_financial_store(
            f"{store_path}.financial.db"
        )

        # ---- Safety plane (spec §33): durable, deterministic restrictions.
        # It reads lockouts from the financial store rather than process memory,
        # so a CRITICAL reconciliation discrepancy still blocks orders after a
        # restart. It is consulted at the last moment before a venue call.
        #
        # The Guardian sits in the adapter rather than here, so it governs every
        # venue call regardless of which component issued the plan. Wiring it
        # at the composition root would leave a second construction path
        # ungoverned, and an ungoverned path is the one that gets used at 3am.
        from kernel.tool_governance import build_execution_guardian

        self.guardian = build_execution_guardian(
            _replay_governance_secret(),
            max_notional=_REPLAY_MAX_NOTIONAL,
        )
        self.adapter = PaperExecutionAdapter(self.paper, guardian=self.guardian)
        self.safety_plane = SafetyPlane(
            self.financial_store, audit=self.store, broker=self.adapter.venue
        )
        self.oms = DurableOrderManager(
            self.financial_store, safety=self.safety_plane, broker=self.adapter.venue
        )
        self.ibor = InvestmentBookOfRecord(
            self.financial_store, mark_provider=self._last_price_of
        )

        # ---- C5 execution chain: plan -> order lifecycle -> venue
        self.order_manager = OrderManager(
            event_bus=self._scoped("c5-execution"),
            adapter=self.adapter,
            quantity_provider=self._plan_quantity,
            durable=self.oms,
            safety=self.safety_plane,
        )

        # ---- Emergency authority + kill switch
        self.risk_governor = RiskGovernor(event_bus=self._scoped("risk-governor"))
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

        # ---- §26 reconciliation: ONE authoritative engine.
        # The legacy per-bar `ReconciliationReport` (positions-only, in-memory,
        # free-text mismatches, no persistence and no route to the safety plane)
        # is retired. This engine is the same one the API and the operator
        # surface read, so there is a single definition of financial consistency
        # and a single durable record of every pass.
        self.reconciliation = ReconciliationEngine(
            self.financial_store,
            account_id=self.oms.account_id,
            safety=self.safety_plane,
        )
        self.reconciliation_runs = 0

        # ---- C11 finance back office
        self.ledger = DoubleEntryLedger(event_bus=self._scoped("c11-finance"))
        self.lot_book = LotBook()
        self.tax_engine = TaxEngine(BUILTIN_RULES["GENERIC_25"])
        self.ca_workflow = CAWorkflow()
        self.surveillance = Surveillance(event_bus=self._scoped("c11-finance"))
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
                AgentIdentity(agent_id="c1-data-fabric", community="C1", role="data", publishes=["aios.c1.data_acquired"]),
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
                    publishes=["aios.c5.order_submitted", "aios.c5.order_filled", "aios.c5.order_executed"],
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
                AgentIdentity(agent_id="c8-evolution", community="C8", role="evolution", publishes=["aios.c8.evolution_triggered"]),
                AgentIdentity(
                    agent_id="c10-world",
                    community="C10",
                    role="world",
                    publishes=[
                        "aios.c10.regime_changed",
                        "aios.c10.expectation_updated",
                        "aios.c10.scenarios_published",
                    ],
                ),
                AgentIdentity(
                    agent_id="c9-governor",
                    community="C9",
                    role="portfolio",
                    publishes=[
                        "aios.c4.opportunity_ranked",
                        "aios.c9.portfolio_allocated",
                        "aios.c9.portfolio_rejected",
                    ],
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

        # Vibe-Trading-style "trust layer": the machine-checkable run card for
        # this replay, populated at summarize time and exposed read-only to
        # the command center (GET /api/v1/run-summary).
        self.run_summary: RunSummary | None = None

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

    def _scoped(self, actor_id: str) -> BaseEventBus:
        """Zero-trust bus view for a community (fails closed off-roster)."""
        from core.event_bus import ScopedEventBus

        allowed = _COMPONENT_BUS_SCOPES.get(actor_id)
        if allowed is None:
            return self.bus
        scoped = ScopedEventBus(self.bus, actor_id, allowed)
        self._scoped_buses.append(scoped)
        return scoped

    @property
    def acl_denials(self) -> list[str]:
        """Every off-roster publish attempt this run (must stay empty)."""
        return [t for scoped in self._scoped_buses for t in scoped.denied]

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
            self._challenge_registry = ChallengeRegistry(
                self.store,
                promotions=self.kernel_bridge.kernel.promotions,
                rollbacks=self.kernel_bridge.kernel.rollbacks,
            )
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
            trial_evaluator=self.evaluate_challenger,
            kernel_bridge=self.kernel_bridge,
            # Same engine instance the per-bar pass uses (B2): findings the
            # UI resolves are verdicts from the reconciliation that ran.
            reconciliation_engine=self.reconciliation,
        )
            # SUPERVISED approvals must reach the real execution path:
            plane._execute_bridge(  # noqa: SLF001 - composition-root wiring
                lambda plan: self.order_manager.on_plan(
                    plan, locked_out=self.risk_governor.locked_out
                )
            )
            # Apply autonomy from settings (fail-closed SUPERVISED default):
            from core.control_plane import AutonomyMode
            try:
                plane.autonomy = AutonomyMode(self.settings.autonomy_mode.upper())
            except (ValueError, AttributeError):
                plane.autonomy = AutonomyMode.SUPERVISED
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
            kernel_bridge=self.kernel_bridge,
            ca_workflow=self.ca_workflow,
            financial_store=self.financial_store,
            ibor=self.ibor,
            safety_plane=self.safety_plane,
            # The same engine instance the per-bar pass uses, so the UI reports
            # on the reconciliation that actually ran rather than a second one.
            reconciliation_engine=self.reconciliation,
            # Serve-time read model: versioned operator settings (B1),
            # latest-bar market fetcher (A5) and recorded debates (A1).
            settings_plane=self.build_settings_plane(),
            market_fetcher=self.build_market_fetcher(),
            debate_sessions=self.build_debate_sessions(),
        )

    def build_market_fetcher(self) -> BaseDataFetcher:
        """Read-only price fetcher backing GET /api/v1/market/candles.

        Mirrors the execution-adapter honesty rule: a live exchange fetcher is
        only constructed on explicit opt-in (``settings.live_market_data`` with
        a real venue id); otherwise the network-free simulated fetcher answers
        so the endpoint reports labelled simulation instead of absence. The
        replay cursor itself is never exposed here — this fetcher answers the
        latest-bar question only and starts no polling.
        """
        if getattr(self.settings, "live_market_data", False):
            exchange_id = str(
                getattr(self.settings, "exchange_id", "") or ""
            ).strip() or "binance"
            try:
                from communities.c1_data.ccxt_fetcher import CcxtDataFetcher

                return CcxtDataFetcher(exchange_id=exchange_id)
            except Exception as exc:  # noqa: BLE001 - live venue unreadable
                logger.warning("live market fetcher unavailable (%s); using simulated", exc)
        from communities.c1_data.data_agent import SimulatedDataFetcher

        return SimulatedDataFetcher()

    def build_settings_plane(self) -> "SettingsPlane":
        """Versioned operator-settings store backing GET/PUT /settings/v1.

        Lives in a sibling of the run store (``<stem>.settings.db`` next to
        ``<stem>.db`` — ``data/aios.settings.db`` for the default serve DB),
        audited into the run's hash chain on every write (256KB cap enforced
        by the plane itself).
        """
        from core.settings_plane import SettingsPlane

        if not hasattr(self, "_settings_plane"):
            sibling = self.store_path.parent / (self.store_path.stem + ".settings.db")
            self._settings_plane = SettingsPlane(sibling, store=self.store)
        return self._settings_plane

    def build_debate_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Recorded debate transcripts backing GET /api/v1/debates.

        The debate engine keeps no session registry — transcripts reach durable
        storage only via the TRANSCRIPT audit events (and only for real LLM
        debates; ``used_llm=false`` fallbacks are never sunk). With
        ``MODEL_PROVIDER=none`` this is empty and the view stays honestly
        absent; with live debates recorded, the view surfaces them.
        """
        sessions: list[dict[str, Any]] = []
        try:
            payloads = self.store.iter_event_payloads("TRANSCRIPT")
        except Exception:  # noqa: BLE001 - debates are best-effort read model
            return sessions
        for payload in payloads[-limit:]:
            raw = payload.get("json")
            if not isinstance(raw, str):
                continue
            try:
                doc = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if isinstance(doc, dict):
                sessions.append(doc)
        return sessions

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

    async def _reconcile(self) -> ReconciliationResult:
        """Per-bar venue-vs-internal comparison through the durable engine (§26).

        The venue here can answer for positions and nothing else, and it says so:
        the snapshot declares ``covers_positions=True`` with orders/executions
        unsupported. That declaration is what keeps this honest — the engine will
        not record a CRITICAL "order missing at the venue" or "execution absent
        from the venue" finding for facets the paper venue was never asked about.

        A divergence is no longer a transient string: it is a persisted
        reconciliation run plus typed findings, and a CRITICAL finding engages a
        durable safety-plane restriction before this method returns. The bus
        event and the emergency escalation are preserved, but they are now driven
        by the durable verdict rather than by a second, weaker definition of
        consistency.
        """
        try:
            venue_positions = self.adapter.positions_snapshot()
        except Exception as exc:  # noqa: BLE001 - an unreadable venue is not a pass
            # The dangerous failure mode is a reconciliation that "passes"
            # because the adapter returned nothing. An unreadable venue is an
            # execution-path failure and is escalated as one; no run is recorded,
            # so no operator can later read a clean verdict that never happened.
            logger.error("venue %s could not be read for reconciliation: %s", self.adapter.venue, exc)
            await self.risk_governor.escalate(
                EmergencyStateValue.EXECUTION_FAILURE,
                f"reconciliation aborted: venue {self.adapter.venue} unreadable ({exc})",
                triggered_by="reconciler",
            )
            raise

        snapshot = snapshot_from_rows(
            broker=self.adapter.venue,
            account_id=self.oms.account_id,
            mode=ReconciliationMode.FULL_SNAPSHOT,
            positions=venue_positions,
            adapter_version=PAPER_RECONCILIATION_ADAPTER,
            # The paper venue reports positions only; it is not asked for, and
            # therefore cannot be judged on, orders or executions.
            covers_orders=False,
            covers_executions=False,
            covers_positions=True,
        )
        result = self.reconciliation.reconcile(snapshot)
        self.reconciliation_runs += 1
        if not result.requires_lockout:
            return result

        await self.bus.publish(EventTopic.RECONCILIATION_FAILED, result.run)
        critical = result.critical()
        await self.risk_governor.escalate(
            EmergencyStateValue.EXECUTION_FAILURE,
            f"reconciliation run {result.run.run_id} raised {len(critical)} critical "
            f"finding(s); lockout scope {result.lockout_scope}",
            triggered_by="reconciler",
        )
        await self.kill_switch.trigger("reconciliation failed", triggered_by="reconciler")
        return result

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

    def _record_durable_exit(
        self, receipt: TradeExecutionReceipt, exit_price: float, reason: str
    ) -> None:
        """Record the closing order + fill in durable state (spec §23, §27).

        Bracket exits are decided by the venue simulation, but they are still
        capital movements: without them the book would only ever see entries.
        The paper venue charges the round trip on the entry fill, so the exit
        leg carries no fee of its own (recorded, not guessed).
        """
        strategy = self._strategies.get(receipt.strategy_id)
        entry_action = strategy.action if strategy else "BUY"
        exit_side = OrderSide.SELL if entry_action == "BUY" else OrderSide.BUY
        client_order_id = f"{receipt.symbol}:{receipt.strategy_id}:exit:{receipt.execution_id}"
        try:
            order = self.oms.prepare_order(
                client_order_id=client_order_id,
                strategy_id=receipt.strategy_id,
                symbol=receipt.symbol,
                side=exit_side,
                quantity=receipt.filled_quantity,
            )
            self.oms.accept(order.internal_order_id)
            self.oms.apply_fill(
                Fill(
                    fill_id=f"exit:{receipt.execution_id}",
                    order_id=order.internal_order_id,
                    broker_execution_id=f"exit:{receipt.execution_id}",
                    symbol=receipt.symbol,
                    side=exit_side,
                    quantity=receipt.filled_quantity,
                    price=exit_price,
                    executed_at=self.fetcher.current_timestamp(),
                )
            )
        except FinancialStoreError as exc:
            logger.error(
                "durable exit recording failed for %s: %s", receipt.execution_id, exc
            )

    async def _settle(self, receipt: TradeExecutionReceipt, exit_price: float, reason: str) -> None:
        pnl_opt = self.paper.settle_position(receipt.execution_id, exit_price)
        if pnl_opt is None:
            logger.warning("Settlement skipped for unknown execution %s", receipt.execution_id)
            return
        self._record_durable_exit(receipt, exit_price, reason)

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
            if self.settings.auto_research:
                await self._auto_research_cycle()
            if self.settings.ml_training:
                self._finalize_models()
            await self.bus.wait_until_idle()
        finally:
            await self.bus.stop()

        summary.experiment_reproducibility_hash = self._experiment_repro_hash
        self.run_summary = summary
        return summary

    async def _auto_research_cycle(self) -> int:
        """UPDATE-HYPOTHESIS-SPACE: synthesize, track, and stage challengers.

        Proposals are UNTESTED knowledge for FUTURE runs; nothing here touches
        the current run's trades, and promotion remains human-gated.
        """
        from research.auto_research import as_candidate

        proposals = self.auto_research.synthesize()
        for proposal in proposals:
            self.auto_research.register(proposal)
            await self.kernel_bridge.on_hypothesis(as_candidate(proposal))
            trial_name = f"auto:{proposal.hypothesis_id[:8]}"
            try:
                registry = self.build_challenge_registry()
                if trial_name not in registry.trials:
                    registry.propose(
                        trial_name,
                        description=f"{proposal.statement[:140]}",
                        metric="pnl",
                    )
            except Exception as exc:  # noqa: BLE001 - staging must not break the loop
                logger.warning("challenger staging skipped for %s: %s", trial_name, exc)
        if proposals:
            logger.info("auto-research proposed %d new hypotheses", len(proposals))
        return len(proposals)

    async def evaluate_challenger(self, name: str) -> dict[str, Any]:
        """Run champion vs challenger over IDENTICAL data in isolated sandboxes.

        Champion = the deterministic families that traded this run; challenger
        adds MLDirectionFamily (the trained direction model as candidate
        generator). Each side gets a fresh runner + separate audit store so
        neither pollutes this run's books. Evidence lands in
        CHALLENGER_EVALUATION; promotion stays a separate human action.
        """
        from communities.c4_strategy.families import DEFAULT_FAMILIES
        from communities.c4_strategy.ml_family import MLDirectionFamily

        registry = self.build_challenge_registry()
        trial = registry._get(name)  # noqa: SLF001 - composition-root access

        def families_factory(side: str) -> list[Any]:
            if side == "challenger":
                return [*DEFAULT_FAMILIES, MLDirectionFamily()]
            return list(DEFAULT_FAMILIES)

        async def run_side(side: str) -> Any:
            base = getattr(self.store, "db_path", Path("data/aios"))
            store_path = Path(f"{base}.trial-{name}-{side}.db")
            sandbox = ReplayRunner(
                csv_path_by_symbol=self.csv_path_by_symbol,
                store_path=store_path,
                initial_balance=self.initial_balance,
                slippage_pct=self.slippage_pct,
                settings=Settings(model_provider="none", auto_research=False),
                shadow_mode=False,
            )
            sandbox.c4.families = families_factory(side)
            return await sandbox.run()

        recommendation = await registry.evaluate(name, run_side, families_factory)
        logger.info(
            "challenger %s evaluated: %s", name, recommendation.get("recommendation")
        )
        _ = trial  # registry owns mutation; kept for clarity
        return recommendation

    def _finalize_models(self) -> None:
        """§12 model lifecycle: train pooled direction model on replay closes.

        Walk-forward evaluation only (fit-on-past, predict-next); the artifact
        hash pins the exact weights; metrics come from the honest loop.
        """
        import csv

        from research.model_lab import train_pooled

        closes_by_symbol: dict[str, list[float]] = {}
        for symbol, path in self.csv_path_by_symbol.items():
            with open(path, newline="", encoding="utf-8") as handle:
                closes_by_symbol[symbol] = [
                    float(row["close"]) for row in csv.DictReader(handle) if row.get("close")
                ]

        result = train_pooled(closes_by_symbol)
        if not result.get("trained"):
            return
        models = self.kernel_bridge.kernel.models
        if models is None:  # pragma: no cover - composition root always attaches the registries
            logger.warning("kernel has no model registry; skipping direction model registration")
            return
        try:
            models.register(
                model_id="direction_logreg",
                version="v1",
                model_type="logistic_regression",
                feature_ref={"feature_id": "ohlcv_passthrough", "version": "v1"},
                metadata={"features": "returns(1,2,3,5)+vol(5,10)+sma ratios; stdlib only"},
            )
        except ValueError:
            return  # already registered this kernel (defensive; one run per kernel)
        models.mark_trained("direction_logreg", "v1", result["artifact_hash"])
        models.mark_evaluated("direction_logreg", "v1", dict(result["metrics"]))
        self.store.append_event(
            "MODEL_TRAINED",
            "direction_logreg:v1",
            {
                "artifact_hash": result["artifact_hash"],
                "metrics": result["metrics"],
                "per_symbol_walk_forward": result.get("per_symbol", {}),
            },
        )
        logger.info(
            "model direction_logreg@v1 trained: %s", json.dumps(result["metrics"], default=str)
        )

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

        # V1-A financial kernel: prove the deterministic book is intact and that
        # live positions equal the immutable fill ledger before we report.
        invariants = self.financial_store.verify_invariants()
        rebuild = self.ibor.rebuild()
        if not invariants.ok:
            logger.error(
                "FINANCIAL INVARIANT VIOLATION: %s",
                [c.name for c in invariants.failures()],
            )
        if not rebuild.ok:
            logger.error("IBOR REBUILD DIVERGENCE: %s", rebuild.divergences)

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
            durable_orders=len(self.financial_store.orders()),
            durable_fills=len(self.financial_store.fills()),
            durable_open_orders=len(self.financial_store.open_orders()),
            financial_invariants_ok=invariants.ok,
            ibor_rebuild_ok=rebuild.ok,
            outbox_backlog=self.financial_store.outbox_backlog(),
        )




