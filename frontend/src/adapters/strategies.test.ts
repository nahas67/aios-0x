import { describe, expect, it } from "vitest";
import { adaptStrategies } from "./strategies";

describe("strategiesAdapter", () => {
  it("maps family rows to view items; uncomputed metrics stay null", () => {
    const out = adaptStrategies({
      strategies: [
        { family: "MOMENTUM", trades: 120, wins: 70, losses: 50, win_rate_pct: 58.3, pnl: 45000, active: true },
        { family: "CARRY", trades: 0, wins: 0, losses: 0, win_rate_pct: 0, pnl: 0, active: false },
      ],
    });
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({
      id: "MOMENTUM",
      name: "MOMENTUM",
      family: "MOMENTUM",
      status: "ACTIVE_PRODUCTION",
      winRatePct: 58.3,
      tradesCount: 120,
      realizedPnl: 45000,
    });
    // No Sharpe / drawdown / capacity engine exists — null renders as "—".
    expect(out[0].currentSharpe).toBeNull();
    expect(out[0].maxDrawdownPct).toBeNull();
    expect(out[0].allocatedUsd).toBeNull();
    expect(out[1].status).toBe("UNDER_REVIEW");
  });

  it("returns an empty list when the backend reports no families", () => {
    expect(adaptStrategies({ strategies: [] })).toEqual([]);
  });
});
