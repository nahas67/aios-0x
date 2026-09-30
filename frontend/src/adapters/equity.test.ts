import { describe, expect, it } from "vitest";
import { adaptEquity } from "./equity";

describe("equityAdapter", () => {
  it("zips three parallel arrays by index", () => {
    const out = adaptEquity({
      equity: [100, 110, 105],
      drawdown_pct: [0, 0, 0.5],
      benchmark: [100, 101, 102],
      start: null,
      end: null,
      points: 3,
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out).toHaveLength(3);
    expect(out[0].nav).toBe(100);
    expect(out[0].intradayPnl).toBe(0);
    expect(out[1].intradayPnl).toBe(10);
    expect(out[1].benchmark).toBe(101);
    expect(out[2].drawdownPct).toBe(0.5);
  });

  it("branches on {available:false}", () => {
    expect(
      adaptEquity({ available: false, reason: "x" } as unknown as import("../api/types").Equity),
    ).toEqual({ unavailable: "x" });
  });
});
