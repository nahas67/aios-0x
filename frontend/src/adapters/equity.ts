/**
 * equityAdapter: /api/v1/equity (three parallel arrays) → TrajectoryDataPoint[].
 * Zipped strictly by index; no interpolation, no invented points.
 */
import type { Equity } from "../api/types";
import type { TrajectoryDataPoint } from "../types";
import { type Unavailable } from "./absent";

function labelFor(index: number, start: number | null, end: number | null, count: number): string {
  if (start != null && end != null && count > 1 && end >= start) {
    const ts = start + ((end - start) * index) / (count - 1);
    // Backend start/end are epoch seconds; guard against millis.
    const ms = ts > 1e12 ? ts : ts * 1000;
    const d = new Date(ms);
    if (!Number.isNaN(d.getTime())) {
      return d.toISOString().slice(11, 16);
    }
  }
  return `P${index}`;
}

export function adaptEquity(
  payload: Equity | { available: false; reason?: string },
): TrajectoryDataPoint[] | Unavailable {
  if ("available" in payload) {
    const reason = payload.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "equity curve unavailable" };
  }
  const n = payload.equity.length;
  if (n === 0) return [];
  const base = payload.equity[0];
  return payload.equity.map((nav, i) => ({
    time: labelFor(i, payload.start, payload.end, n),
    nav,
    intradayPnl: nav - base,
    benchmark: payload.benchmark[i] ?? 0,
    drawdownPct: payload.drawdown_pct[i] ?? 0,
    // The backend publishes no utilization series; 0 keeps the chart honest.
    capitalUtilizationPct: 0,
  }));
}
