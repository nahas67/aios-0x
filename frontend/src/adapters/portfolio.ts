/**
 * portfolioAdapter: /api/v1/portfolio → zip AllocationSegment rows.
 * Only allocation_pct + nav are backend-sourced; risk/correlation/drawdown
 * contributions are not computed server-side and stay 0.
 */
import type { Portfolio } from "../api/types";
import type { AllocationSegment } from "../types";
import { type Unavailable } from "./absent";

const PALETTE = ["#00f0ff", "#38bdf8", "#818cf8", "#10b981", "#eab308", "#ec4899", "#22c55e"];

export function adaptPortfolio(
  payload: Portfolio | { available: false; reason?: string },
): AllocationSegment[] | Unavailable {
  if ("available" in payload) {
    const reason = payload.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "portfolio unavailable" };
  }
  return Object.entries(payload.allocation_pct ?? {})
    .sort(([, a], [, b]) => b - a)
    .map(([name, pct], i) => ({
      id: `alloc-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
      name,
      color: PALETTE[i % PALETTE.length],
      currentExposurePct: pct,
      targetExposurePct: pct,
      notionalUsd: (payload.nav * pct) / 100,
      riskContributionPct: 0,
      correlation: 0,
      drawdownContributionPct: 0,
    }));
}
