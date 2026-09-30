/**
 * strategiesAdapter: /api/v1/strategies family rows → strategy cards.
 *
 * Backend: {strategies:[{family, trades, wins, losses, win_rate_pct, pnl,
 *            active}]}. There is no Sharpe / drawdown / capacity engine, so
 * those view fields are null and render as "—", never client-computed.
 */
import type { StrategyRow } from "../api/types";

export interface StrategyItemView {
  id: string;
  name: string;
  family: string;
  targetSharpe: number | null;
  currentSharpe: number | null;
  maxDrawdownPct: number | null;
  capacityUsd: number | null;
  allocatedUsd: number | null;
  status: "ACTIVE_PRODUCTION" | "UNDER_REVIEW";
  winRatePct: number;
  tradesCount: number;
  realizedPnl: number;
}

export function adaptStrategies(payload: { strategies: StrategyRow[] }): StrategyItemView[] {
  return (payload.strategies ?? []).map((s) => ({
    id: s.family,
    name: s.family,
    family: s.family,
    targetSharpe: null,
    currentSharpe: null,
    maxDrawdownPct: null,
    capacityUsd: null,
    allocatedUsd: null,
    status: s.active ? "ACTIVE_PRODUCTION" : "UNDER_REVIEW",
    winRatePct: s.win_rate_pct ?? 0,
    tradesCount: s.trades ?? 0,
    realizedPnl: s.pnl ?? 0,
  }));
}
