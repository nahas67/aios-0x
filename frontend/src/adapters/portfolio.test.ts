import { describe, expect, it } from "vitest";
import { adaptPortfolio } from "./portfolio";

describe("portfolioAdapter", () => {
  it("maps allocation_pct to AllocationSegment rows", () => {
    const out = adaptPortfolio({
      nav: 1000,
      cash: 400,
      open_notional: 600,
      exposure_pct: 60,
      allocation_pct: { CRYPTO: 40, EQUITY: 20 },
      closed_trades: 3,
      realized_pnl: 12.5,
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out).toHaveLength(2);
    const crypto = out.find((s) => s.name === "CRYPTO");
    expect(crypto).toMatchObject({ currentExposurePct: 40, notionalUsd: 400 });
  });

  it("branches on {available:false}", () => {
    expect(
      adaptPortfolio({ available: false, reason: "w" } as unknown as import("../api/types").Portfolio),
    ).toEqual({ unavailable: "w" });
  });
});
