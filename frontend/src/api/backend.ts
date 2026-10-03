/**
 * Domain API modules — one function per backend endpoint, fully typed.
 * Components never construct URLs themselves.
 *
 * Ported from the v1 frontend's endpoints.ts. Deliberately dropped:
 * metricsText() — it called res.json() on a Prometheus text body and
 * always threw. Read /metrics as text where needed instead.
 */
import { http } from "./client";
import type {
  Agent,
  Alert,
  Approval,
  ArenaView,
  AuditRow,
  BacktestResult,
  CalibrationReport,
  ChatResponse,
  ControlResult,
  DebatesView,
  DecisionDrilldown,
  Equity,
  EvaluationRecord,
  Executive,
  Gates,
  GlobalEvent,
  Graduation,
  Opportunity,
  Health,
  HypothesisDetail,
  KnowledgeSummary,
  MarketCandles,
  MarketInstrument,
  ModelVersion,
  RegistryModel,
  Order,
  Pnl,
  PlatformEvent,
  Portfolio,
  Position,
  Regime,
  RiskState,
  SettingsV1PutResult,
  SettingsV1View,
  SettingsView,
  StrategyRow,
  KernelBookOfRecord,
  KernelCash,
  KernelFill,
  KernelHealth,
  KernelInvariants,
  KernelOrder,
  KernelOrderDetail,
  KernelOutbox,
  KernelPositions,
  KernelReconciliation,
  Unavailable,
} from "./types";

const v1 = "/api/v1";

export const executiveApi = {
  get: () => http.get<Executive>(`${v1}/executive`),
  health: () => http.get<Health>(`${v1}/health`),
  gates: () => http.get<Gates>(`${v1}/gates`),
};

export const portfolioApi = {
  portfolio: () => http.get<Portfolio>(`${v1}/portfolio`),
  positions: () => http.get<{ positions: Position[] }>(`${v1}/positions`),
  orders: () => http.get<{ orders: Order[] }>(`${v1}/orders`),
  executions: () => http.get<{ executions: Execution[] }>(`${v1}/executions`),
  equity: () => http.get<Equity>(`${v1}/equity`),
  pnl: () => http.get<Pnl>(`${v1}/pnl`),
  strategies: () => http.get<{ strategies: StrategyRow[] }>(`${v1}/strategies`),
  graduation: () => http.get<Graduation>(`${v1}/graduation`),
};

export interface Execution {
  execution_id: string;
  symbol: string | null;
  fill_price: number | null;
  realized_pnl: number;
  action: string | null;
  confidence_pct: number | null;
  exit_reason: string | null;
}

export const riskApi = {
  risk: () => http.get<RiskState>(`${v1}/risk`),
  accounting: () => http.get<Record<string, unknown>>(`${v1}/accounting`),
};

/**
 * Durable financial kernel (V1-A.2). Read-only by construction: every function
 * here is a GET. The one financial mutation reachable over HTTP is the audited,
 * RBAC-gated lockout release in `controlApi`, and it never appears on a page
 * that a viewer can reach.
 *
 * Each endpoint can answer `{ available: false, reason }`, so callers receive a
 * union and the views render "unknown" instead of an invented empty book.
 */
export const kernelApi = {
  ibor: () => http.get<KernelBookOfRecord | Unavailable>(`${v1}/financial/ibor`),
  positions: () => http.get<KernelPositions | Unavailable>(`${v1}/financial/positions`),
  cash: () => http.get<KernelCash | Unavailable>(`${v1}/financial/cash`),
  orders: (limit = 100) =>
    http.get<{ available: true; orders: KernelOrder[] } | Unavailable>(
      `${v1}/financial/orders?limit=${limit}`,
    ),
  order: (id: string) =>
    http.get<KernelOrderDetail | Unavailable>(`${v1}/financial/orders/${encodeURIComponent(id)}`),
  fills: (limit = 100) =>
    http.get<{ available: true; fills: KernelFill[] } | Unavailable>(
      `${v1}/financial/fills?limit=${limit}`,
    ),
  invariants: () => http.get<KernelInvariants | Unavailable>(`${v1}/financial/invariants`),
  health: () => http.get<KernelHealth | Unavailable>(`${v1}/financial/health`),
  outbox: (limit = 50) =>
    http.get<KernelOutbox | Unavailable>(`${v1}/financial/outbox?limit=${limit}`),
  reconciliation: (limit = 20) =>
    http.get<KernelReconciliation | Unavailable>(`${v1}/financial/reconciliation?limit=${limit}`),
};

export const researchApi = {
  research: () => http.get<CalibrationReport>(`${v1}/research`),
  knowledge: () => http.get<KnowledgeSummary>(`${v1}/knowledge`),
  hypothesis: (id: string) => http.get<HypothesisDetail>(`${v1}/knowledge/${encodeURIComponent(id)}`),
  memory: () => http.get<Record<string, unknown>>(`${v1}/memory`),
  decisions: (executionId: string) =>
    http.get<DecisionDrilldown>(`${v1}/decisions/${encodeURIComponent(executionId)}`),
  backtest: (closes: number[], train_bars = 90, test_bars = 30) =>
    http.post<BacktestResult>(`${v1}/research/backtest`, { closes, train_bars, test_bars }),
};

/**
 * Champion/challenger arena (ARCHITECTURE.txt §2 layer 25). Read-only by
 * construction — there is no POST here.
 *
 * Every mutation in this domain is an audited control action (`evaluate_trial`,
 * `promote_challenger`) and goes through `controlApi` via `lib/control.ts`, so the
 * server stays the only RBAC authority. Putting a promote call next to this one
 * would be an invitation to bypass it, which is why this group stays GET-only.
 *
 * The endpoint answers with `wired: false` rather than `{available: false}`, and
 * that is deliberate on the server's side: an arena that cannot be read is a
 * different fact from one holding nothing. See `adapters/arena.ts`.
 */
export const arenaApi = {
  arena: () => http.get<ArenaView>(`${v1}/arena`),
};

export const marketApi = {
  candles: (symbol: string, tf: string) =>
    http.get<MarketCandles>(
      `${v1}/market/candles?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tf)}`,
    ),
  instruments: () => http.get<{ instruments: MarketInstrument[] }>(`${v1}/market/instruments`),
};

export const debatesApi = {
  debates: () => http.get<DebatesView>(`${v1}/debates`),
};

export const settingsV1Api = {
  get: () => http.get<SettingsV1View>(`${v1}/settings/v1`),
  put: (settings: Record<string, unknown>) =>
    http.put<SettingsV1PutResult>(`${v1}/settings/v1`, settings),
};

export const intelligenceApi = {
  agents: () => http.get<{ agents: Agent[] }>(`${v1}/agents`),
  opportunities: () => http.get<{ opportunities: Opportunity[] }>(`${v1}/opportunities`),
  regimes: () => http.get<{ regimes: Regime[] }>(`${v1}/regimes`),
  events: () => http.get<{ events: GlobalEvent[] }>(`${v1}/events`),
  alerts: () => http.get<{ alerts: Alert[] }>(`${v1}/alerts`),
  platformEvents: (limit = 100) =>
    http.get<{ events: PlatformEvent[] }>(`${v1}/platform-events?limit=${limit}`),
};

export const modelsApi = {
  models: () => http.get<{ available: boolean; models: ModelVersion[] }>(`${v1}/models`),
  /**
   * The governance view's endpoint.
   *
   * `/models` returns raw ModelRegistry.list_versions() output, which does not
   * carry `evaluation_metrics` -- the field the claim gate reads. `/models/registry`
   * is reshaped for exactly this purpose and returns
   * `{available: false, models: []}` rather than a fabricated roster.
   */
  registry: () =>
    http.get<{ available: boolean; models: RegistryModel[]; reason?: string }>(
      `${v1}/models/registry`,
    ),
  evaluations: () => http.get<{ evaluations: EvaluationRecord[] }>(`${v1}/evaluations`),
};

export interface AuditVerify {
  valid: boolean;
  blocks_checked: number;
  head_hash: string;
  breaks: { seq: number; reason: string }[];
}

export const auditApi = {
  audit: (query = "", limit = 50) =>
    http.get<{ audit: AuditRow[] }>(
      `${v1}/audit?limit=${limit}${query ? `&q=${encodeURIComponent(query)}` : ""}`,
    ),
  verify: () => http.get<AuditVerify>(`${v1}/audit/verify`),
};

export const settingsApi = {
  settings: () => http.get<SettingsView>(`${v1}/settings`),
};

export const approvalsApi = {
  approvals: () => http.get<{ approvals: Approval[] }>(`${v1}/approvals`),
};

// ------------------------------------------------------------------ control

export interface ControlBody {
  operator_id: string;
  role: string;
  params?: Record<string, string | number>;
}

export const controlApi = {
  execute: (action: string, body: ControlBody) =>
    http.post<ControlResult>(`${v1}/control/${encodeURIComponent(action)}`, body),
  // Only `message` is sent. The server resolves operator identity and role from its own
  // token map and ignores anything in the body (`api/server.py` `_resolve_request_identity`),
  // so passing them here implied a client-side authority that does not exist and would be
  // actively misleading to anyone reading this call site.
  chat: (body: { message: string }) => http.post<ChatResponse>(`${v1}/chat`, body),
};

export type {
  Opportunity,
  DecisionDrilldown,
  BacktestResult,
  BacktestWindow,
  DebateSessionWire,
  DebateTurnWire,
  DebatesView,
  MarketCandle,
  MarketCandles,
  MarketIndicators,
  MarketInstrument,
  SettingsV1PutResult,
  SettingsV1View,
} from "./types";
