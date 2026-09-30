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
  AuditRow,
  CalibrationReport,
  ChatResponse,
  ControlResult,
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
  ModelVersion,
  Order,
  Pnl,
  PlatformEvent,
  Portfolio,
  Position,
  Regime,
  RiskState,
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
  evaluations: () => http.get<{ evaluations: EvaluationRecord[] }>(`${v1}/evaluations`),
};

export const auditApi = {
  audit: (query = "", limit = 50) =>
    http.get<{ audit: AuditRow[] }>(
      `${v1}/audit?limit=${limit}${query ? `&q=${encodeURIComponent(query)}` : ""}`,
    ),
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
  chat: (body: { operator_id: string; role: string; message: string }) =>
    http.post<ChatResponse>(`${v1}/chat`, body),
};

export type { Opportunity, DecisionDrilldown } from "./types";
