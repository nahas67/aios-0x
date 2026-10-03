/**
 * Typed models mirroring the Python engine's JSON contracts
 * (api/views.py, schemas/contracts.py, core/control_plane.py).
 * Kept intentionally tolerant: optional fields where the backend
 * legitimately omits them (e.g. synthetic mode without providers).
 */

// ---------------------------------------------------------------- executive

export interface Executive {
  cash_balance: number | null;
  open_positions: number;
  cumulative_realized_pnl: number;
  closed_trades: number;
  emergency_state: string;
  drawdown_pct: number | null;
  chain_valid: boolean;
  events_logged: number;
  predictions_scored: number;
  postmortems: number;
  paused: boolean | null;
}

export interface Health {
  audit_chain_valid: boolean;
  first_bad_seq: number | null;
  counts: Record<string, number>;
  components: {
    ledger_wired: boolean;
    governor_wired: boolean;
    risk_governor_wired: boolean;
    paper_engine_wired: boolean;
  };
}

export interface Gate {
  gate: string;
  title: string;
  status: string;
  how_to_unblock: string;
}

export interface Gates {
  execution_environment: "PAPER" | "SHADOW" | string;
  autonomy: string;
  live_capital_approved_by: string | null;
  live_routing_enabled: boolean;
  gates: Gate[];
  production_allowed: boolean;
}

// ----------------------------------------------------------------- portfolio

export interface Portfolio {
  nav: number;
  cash: number | null;
  open_notional: number;
  exposure_pct: number;
  allocation_pct: Record<string, number>;
  closed_trades: number;
  realized_pnl: number;
}

export interface Position {
  execution_id: string;
  symbol: string;
  action: string;
  qty: number;
  entry: number;
  mark: number;
  unrealized: number;
  stop: number | null;
  target: number | null;
  mark_value: number;
  asset_class: string;
}

export interface Order {
  client_order_id: string;
  symbol: string;
  side: string;
  status: string;
  quantity: number;
  avg_fill_price: number | null;
  reject_reason: string | null;
  created_at: string;
}

export interface Execution {
  execution_id: string;
  symbol: string | null;
  fill_price: number | null;
  realized_pnl: number;
  action: string | null;
  confidence_pct: number | null;
  exit_reason: string | null;
}

export interface Equity {
  equity: number[];
  drawdown_pct: number[];
  benchmark: number[];
  start: number | null;
  end: number | null;
  points: number;
}

export interface PnlBucket {
  trades: number;
  wins: number;
  pnl: number;
}

export interface Pnl {
  totals: PnlBucket & { win_rate_pct: number; fees: number };
  by_family: Record<string, PnlBucket>;
  by_symbol: Record<string, PnlBucket>;
}

export interface StrategyRow {
  family: string;
  trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  pnl: number;
  active: boolean;
}

// --------------------------------------------------------------------- risk

export interface RiskTransition {
  new_state: string;
  reason: string;
  triggered_by: string | null;
  lockout_engaged: boolean;
}

export interface RiskState {
  current_state: string | null;
  locked_out: boolean | null;
  drawdown_pct: number | null;
  halt_dd_pct: number | null;
  max_class_exposure_pct: number | null;
  class_exposures_pct: Record<string, number>;
  recent_transitions: RiskTransition[];
  compliance_alerts: Record<string, unknown>[];
  emergency_events: Record<string, unknown>[];
}

/**
 * Provenance state of one reported figure, produced by the statistical claim
 * gate (`core/claim_gate.py`, goal G190). A criterion whose claim is not
 * `REPORTABLE` carries a measured value that must not be quoted as a result:
 * it is missing a defined universe, an out-of-sample window, a confidence
 * interval, or one of the other required fields.
 */
export interface ClaimGateState {
  status: "REPORTABLE" | "NOT_REPORTABLE" | "NO_CLAIM";
  reportable: boolean;
  present: string[];
  missing: string[];
}

export interface GraduationCriterion {
  name: string;
  current: number;
  threshold: number;
  op: string;
  pass: boolean;
  claim: ClaimGateState;
}

export interface Graduation {
  ready_for_live: false;
  paper_criteria_pass: boolean;
  criteria: GraduationCriterion[];
  claim_status: ClaimGateState["status"];
  required_fields: string[];
  note: string;
}

// --------------------------------------------------------------- intelligence

export interface Agent {
  agent_id: string;
  community: string | null;
  role: string | null;
  version: string | null;
  publishes: string[];
  reputation: number | null;
}

export interface Opportunity {
  strategy_id: string;
  symbol: string | null;
  family: string | null;
  edge_proxy: number | null;
  expected_rr: number | null;
  alpha_decay: number | null;
  composite_rank: number | null;
}

export interface Regime {
  symbol: string;
  trend: string;
  vol_regime: string;
  realized_vol_pct: number | null;
  window_bars: number | null;
}

export interface PlatformEvent {
  kind: string;
  occurred_at?: string;
  [key: string]: unknown;
}

export interface GlobalEvent {
  kind: string;
  label: string;
  ts: string | null;
  title: string;
  symbol?: string | null;
  severity: string;
  payload: Record<string, unknown>;
}

export interface Alert {
  severity: string;
  category: string;
  message: string;
  symbol?: string | null;
  ts: string | null;
}

export interface Approval {
  plan_id: string;
  symbol: string | null;
  action: string | null;
  entry_price: number | null;
  position_size_pct: number | null;
  status: string;
}

// ------------------------------------------------------------------ research

export interface AuditRow {
  seq: number;
  ts: string;
  kind: string;
  ref_id: string | null;
  payload: Record<string, unknown>;
}

export interface CalibrationBucket {
  bucket: string;
  predicted: number;
  observed: number;
  count: number;
}

export interface CalibrationReport {
  report_id: string;
  created_at: string;
  total_scored: number;
  brier_score: number;
  directional_accuracy_pct: number;
  buckets: CalibrationBucket[];
  reliable: boolean;
}

export interface KnowledgeSummary {
  available: boolean;
  total?: number;
  by_status?: Record<string, number>;
  recent?: KnowledgeRow[];
}

export interface KnowledgeRow {
  hypothesis_id: string;
  statement: string;
  symbol: string | null;
  status: string;
  confidence: number | null;
  evidence_total: number;
  supports: number;
  contradicts: number;
  outcomes: number;
  last_updated: string;
}

export interface HypothesisDetail {
  hypothesis_id: string;
  statement: string;
  rationale: string | null;
  expected_outcome: string | null;
  assumptions: string[];
  symbol: string | null;
  timeframe: string | null;
  expected_risk_reward_ratio: number | null;
  status: string;
  confidence: number | null;
  parent_hypotheses: string[];
  dataset_ref: string | null;
  first_seen: string;
  last_updated: string;
  evidence: {
    evidence_id: string;
    source: string;
    relationship: string;
    confidence: number | null;
    claims: string[];
    counter_claims: string[];
    content_hash: string;
    retrieval_time: string;
  }[];
}

export interface DecisionDrilldown {
  execution_id: string;
  decision: {
    action: string | null;
    symbol: string | null;
    family: string | null;
    position_size_pct: number | null;
  };
  reason: { thesis: string | null };
  evidence: { supporting_arguments: string[]; counter_arguments: string[] };
  verification: {
    confidence_score: number | null;
    fact_score: number | null;
    balance_score: number | null;
    math_score: number | null;
    flagged_hallucinations: string[];
  };
  risk: { stop_loss_price: number | null; take_profit_price: number | null };
  outcome: {
    actual_pnl: number | null;
    exit_reason: string | null;
    direction_correct: boolean | null;
    lessons_learned: string[];
  };
  chain_complete: boolean;
}

// -------------------------------------------------------------------- models

export interface ModelVersion {
  model_id: string;
  version: string;
  status: string;
  artifact_hash?: string;
  created_at?: string;
  evaluation_metrics?: Record<string, unknown>;
  walk_forward?: Record<string, unknown>;
  per_symbol?: Record<string, unknown>;
}

/**
 * A row from `/api/v1/models/registry`.
 *
 * Distinct from `ModelVersion` because it is a different endpoint's shape, not
 * a rename: the registry view reshapes `list_versions()` into an id/name pair
 * and answers `{available: false, models: []}` when nothing is wired. The
 * governance view reads this one, because `/models` does not carry
 * `evaluation_metrics`, which is the field the claim gate needs.
 */
export interface RegistryModel {
  id: string;
  name: string;
  version: string;
  status?: string | null;
  model_type?: string | null;
  artifact_hash?: string;
  created_at?: string | null;
  evaluation_metrics?: Record<string, unknown>;
  walk_forward?: Record<string, unknown>;
}

export interface EvaluationRecord {
  evaluation_id: string;
  subject_type: string;
  subject_ref: string;
  evaluator: string;
  verdict: string;
  dimensions: Record<string, unknown>;
  evidence_refs: string[];
  created_at: string;
  summary: string;
}

// ---------------------------------------------- champion/challenger (layer 25)
//
// GET /api/v1/arena is the read model for ARCHITECTURE.txt §2 layer 25.
//
// TWO FLAGS THAT MUST NOT COLLAPSE INTO EACH OTHER, and which is why this is not
// modelled as `{ available: boolean, trials: [] }`:
//
//   `wired`       — is a ChallengeRegistry attached to the composition root at all?
//                   FALSE IS A WIRING FACT, NOT AN EMPTY ARENA. The server can read
//                   the endpoint perfectly well and still have nothing registered to
//                   report, so `wired: false` carries `trials: []` with a note saying
//                   exactly that. Rendering it as "no trials" would state that an
//                   operator asked and was told there are none, which nobody did.
//   `kernel_wired` — are the promotion and rollback controllers attached? Promotion
//                   REFUSES without them, so the flag decides whether the buttons will
//                   work, and an operator must be able to see that BEFORE pressing one.
//
// `recommendation` is a discriminated union on `recommendation` itself, not a
// loose bag of optional numbers. `INSUFFICIENT_EVIDENCE` is what `recommend()`
// returns until BOTH sides have been run: it carries no metric, no margin and no
// comparison, and the type therefore has nowhere to put a number that could be
// rendered as a loss.

/** One side of a trial. `null` on a trial means the side was never run. */
export interface ArenaSide {
  side: string;
  trades: number;
  pnl: number;
  directional_accuracy_pct: number;
  max_drawdown_pct: number;
}

export interface ArenaRecommendationInsufficient {
  recommendation: "INSUFFICIENT_EVIDENCE";
  /** Never present. There is nothing to compare, so there is nothing to report. */
  metric?: undefined;
  champion?: undefined;
  challenger?: undefined;
  margin?: undefined;
  note?: string;
}

export interface ArenaRecommendationCompared {
  recommendation: "PROMOTE" | "REJECT";
  metric?: string;
  champion?: number;
  challenger?: number;
  margin?: number;
  note?: string;
}

export type ArenaRecommendation =
  | ArenaRecommendationInsufficient
  | ArenaRecommendationCompared;

/** The EvaluationRecord attached to a trial. Promotion is refused without one. */
export interface ArenaVerdict {
  evaluation_id: string;
  verdict: string;
  evaluator: string;
  summary: string;
  created_at: string;
}

export interface ArenaTrial {
  name: string;
  description: string;
  metric: string;
  state: "PROPOSED" | "EVALUATED" | "PROMOTED" | "REJECTED";
  promoted_by: string | null;
  evaluated_at: string | null;
  champion: ArenaSide | null;
  challenger: ArenaSide | null;
  recommendation: ArenaRecommendation;
  verdict: ArenaVerdict | null;
  notes: string[];
}

export interface ArenaView {
  wired: boolean;
  kernel_wired: boolean;
  trials: ArenaTrial[];
  note: string;
}

// ------------------------------------------------- market chart (Phase: A5)
//
// GET /api/v1/market/candles?symbol=&tf= answers either
// {available:true, symbol, tf, candles:[{time,open,high,low,close,volume}],
//  indicators:{ema20,ema50,rsi14,macd,bollinger}, source}
// or {available:false, reason}. Every indicator is null when the real
// series is too short — render "—", never invent a value.

export interface MarketCandle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketIndicators {
  ema20: number | null;
  ema50: number | null;
  rsi14: number | null;
  macd: number | null;
  bollinger: { upper: number; middle: number; lower: number } | null;
}

export type MarketCandles =
  | {
      available: true;
      symbol: string;
      tf: string;
      candles: MarketCandle[];
      indicators: MarketIndicators;
      source?: string | null;
    }
  | { available: false; reason: string };

export interface MarketInstrument {
  symbol: string;
  name: string;
  category: string;
}

// ------------------------------------------------- debates (Phase: A1)
//
// GET /api/v1/debates answers {available:true, debates:[...]} or
// {available:false, reason} (e.g. MODEL_PROVIDER=none with no sessions).

export interface DebateTurnWire {
  agentId: string;
  stance: string;
  thesis: string;
  confidencePct: number | null;
}

export interface DebateSessionWire {
  id: string;
  symbol: string | null;
  side: string;
  status: string;
  consensusScorePct: number | null;
  turns: DebateTurnWire[];
}

export type DebatesView =
  | { available: true; debates: DebateSessionWire[] }
  | { available: false; reason: string };

// ------------------------------------------------- settings plane (Phase: B1)
//
// GET /api/v1/settings/v1 answers
//   {available:true, version, settings} (empty object at version 0)
// or {available:false, reason} when the plane is not wired.
// PUT /api/v1/settings/v1 takes the raw settings object and answers
// {version, settings}. PUT is fail-closed: 401 without a bearer token.

export type SettingsV1View =
  | { available: true; version: number; settings: Record<string, unknown> }
  | { available: false; reason: string };

export interface SettingsV1PutResult {
  version: number;
  settings: Record<string, unknown>;
}

// ------------------------------------------------- backtest (Phase: B4)
//
// POST /api/v1/research/backtest {closes (cap 5000), train_bars, test_bars}
// answers {sharpe, max_dd_pct, points, train_bars, test_bars, windows}.

export interface BacktestWindow {
  window_index: number;
  start: number;
  end: number;
  test_sharpe: number | null;
  test_max_dd_pct: number | null;
}

export interface BacktestResult {
  sharpe: number | null;
  max_dd_pct: number | null;
  points: number;
  train_bars: number;
  test_bars: number;
  windows: BacktestWindow[];
}

// ------------------------------------------------------------------ settings

export interface SettingsView {
  system: {
    model_provider: string;
    research_mode: string;
    llm_configured: boolean;
    shadow_mode: boolean;
  };
  ai: {
    research_model_cheap: string | null;
    research_model_reasoning: string | null;
    verification_model: string | null;
    llm_temperature: number | null;
  };
  data: {
    finnhub: boolean;
    gnews: boolean;
    newsdata: boolean;
    marketstack: boolean;
    fred: boolean;
  };
  risk: {
    max_class_exposure_pct: number | null;
    halt_dd_pct: number | null;
    warning_dd_pct: number | null;
    caution_dd_pct: number | null;
  };
  execution_rails: {
    environment: string;
    paper_capability: boolean;
    testnet_capability: boolean;
    live_adapter_available: boolean;
    live_execution_allowed_env: boolean;
    live_routing_enabled: boolean;
    live_capital_approval_recorded: boolean;
    constitution_live_routing: boolean;
    micro_live_cap_usd: number;
    constitution_pinned: boolean;
  };
  autonomy: string | null;
  pending_approvals: number;
}

// -------------------------------------------------------------------- stream

export interface StreamFrame {
  ts: number;
  executive: Executive;
  platform_tail: PlatformEvent[];
}

// --------------------------------------------------------------------- chat

export interface EvidenceRef {
  label: string;
  source: string;
  available: boolean;
  rows: number | null;
  detail: string;
}

export interface AdvisoryAnswer {
  /** Literal on the server. Rendered prominently: an advisory is not an authorization. */
  authority: "ADVISORY";
  agent_id: string;
  community: string;
  role: string;
  question: string;
  answer: string;
  /** RECORDED = the agent's own published record. MODEL = a model phrased it. UNKNOWN = no
   *  readable evidence, and nothing was inferred from the gap. */
  stance: "RECORDED" | "MODEL" | "UNKNOWN" | string;
  evidence: EvidenceRef[];
  /** Action NAMES. Nothing on the server can execute them; they are prompts for a human. */
  proposed_actions: string[];
  attribution: { mode: "deterministic" | "model" | string; provider?: string; model?: string; note: string };
  limitations: string[];
}

export interface ChatResponse {
  kind: "query" | "command" | "advisory" | "error" | "denied" | "help" | string;
  answer: string;
  /** Present on kind === "advisory". */
  advisory?: AdvisoryAnswer;
  agent?: string | null;
  authority?: string;
  query?: string;
  action?: string;
  result?: unknown;
  [key: string]: unknown;
}

// ------------------------------------------------------------------- control

export interface ControlResult {
  operator_id: string;
  role: string;
  action: string;
  authorized: boolean;
  params: Record<string, unknown>;
  result?: Record<string, unknown>;
}

// ------------------------------------------------ durable financial kernel (V1-A.2)
//
// Every one of these payloads can come back as { available: false, reason } when
// the durable kernel is not wired into the serving process. The views must show
// that honestly rather than rendering an empty book, so `available` is part of
// the contract instead of an optional nicety.

export interface Unavailable {
  available: false;
  reason: string;
}

export interface KernelPosition {
  account_id: string;
  symbol: string;
  quantity: number;
  avg_cost: number;
  realized_pnl: number;
  fees_paid: number;
  updated_at: string;
}

export interface KernelPositions {
  available: true;
  positions: KernelPosition[];
}

export interface KernelCashRow {
  account_id: string;
  currency: string;
  settled_minor: number;
  reserved_minor: number;
  available_minor: number;
}

export interface KernelReservation {
  reservation_id: string;
  account_id: string;
  currency: string;
  amount_minor: number;
  reason: string;
  order_id: string | null;
  active: boolean;
  created_at: string;
}

export interface KernelCash {
  available: true;
  cash: KernelCashRow[];
  reservations: KernelReservation[];
}

export interface KernelOrder {
  internal_order_id: string;
  client_order_id: string;
  broker_order_id: string | null;
  strategy_id: string;
  symbol: string;
  side: string;
  quantity: number;
  filled_quantity: number;
  status: string;
  version: number;
  created_at: string;
}

export interface KernelOrderDetail {
  available: true;
  order: KernelOrder;
  transitions: {
    from_status: string | null;
    to_status: string;
    actor: string;
    reason: string | null;
    occurred_at: string;
  }[];
  fills: {
    fill_id: string;
    broker_execution_id: string | null;
    quantity: number;
    price: number;
    fee: number;
    currency: string;
    executed_at: string;
  }[];
}

export interface KernelFill {
  fill_id: string;
  order_id: string;
  broker_execution_id: string | null;
  account_id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  fee: number;
  strategy_id: string | null;
  executed_at: string;
}

export interface KernelInvariants {
  available: true;
  ok: boolean;
  checked: number;
  failures: { name: string; detail: string }[];
}

export interface KernelSafetyState {
  blocked?: boolean;
  reasons?: string[];
  lockouts?: {
    lockout_id: string;
    scope: string;
    subject: string;
    reason: string;
    engaged_by: string;
    engaged_at: string;
  }[];
  [key: string]: unknown;
}

export interface KernelHealth {
  available: true;
  backend?: string;
  reachable?: boolean;
  schema?: {
    dialect?: string;
    current?: number;
    required?: number;
    up_to_date?: boolean;
  };
  outbox_backlog?: number;
  dead_letters?: number;
  open_findings?: number;
  active_lockouts?: number;
  safety?: KernelSafetyState;
  [key: string]: unknown;
}

export interface KernelEventBackbone {
  wired: boolean;
  reason?: string;
  backend?: string;
  url?: string;
  stream?: string;
  connected?: boolean;
  server?: string | null;
  reconnect_count?: number | null;
  published?: number;
  publish_failures?: number;
  consumer_lag: number | null;
  [key: string]: unknown;
}

export interface KernelOutbox {
  available: true;
  backlog: number;
  dead_letter_count: number;
  event_backbone?: KernelEventBackbone;
  dead_letters: {
    event_id: string;
    event_type: string;
    attempts: number;
    last_error: string | null;
  }[];
  pending: {
    event_id: string;
    event_type: string;
    status: string;
    attempts: number;
    claimed_by: string | null;
  }[];
}

export interface KernelReconciliationRun {
  run_id: string;
  mode: string;
  broker: string | null;
  adapter_version: string | null;
  window_start: string | null;
  window_end: string | null;
  cursor_token: string | null;
  queried_at: string | null;
  started_at: string;
  finished_at: string | null;
  matched_executions: number;
  broker_only_executions: number;
  internal_only_executions: number;
  finding_count: number;
  ok: boolean;
  lockout_scope: string;
}

export interface KernelFinding {
  finding_id: string;
  run_id: string;
  kind: string;
  severity: string;
  subject: string;
  detail: string;
  internal_value: string | null;
  broker_value: string | null;
  status: string;
  scope: string;
  created_at: string;
}

export interface KernelReconciliation {
  available: true;
  last_run: KernelReconciliationRun | null;
  runs: {
    run_id: string;
    mode: string;
    started_at: string;
    matched_executions: number;
    finding_count: number;
    ok: boolean;
    lockout_scope: string;
  }[];
  open_findings: KernelFinding[];
  lockouts: KernelSafetyState | null;
}

export interface KernelIborPosition {
  symbol: string;
  quantity: number;
  avg_cost: number;
  mark_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
  currency: string;
}

export interface KernelIborCash {
  account_id: string;
  currency: string;
  settled_minor: number;
  reserved_minor: number;
  available_minor: number;
}

export interface KernelBookOfRecord {
  available: true;
  snapshot_id: string;
  as_of: string;
  account_id: string;
  cash: KernelIborCash[];
  positions: KernelIborPosition[];
  open_orders: KernelOrder[];
  nav: number | null;
  gross_exposure: number | null;
  net_exposure: number | null;
  realized_pnl: number;
  unrealized_pnl: number | null;
  fills_applied: number;
  /** False when at least one symbol has no mark — NAV is then not trustworthy. */
  marks_complete: boolean;
}
