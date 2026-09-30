import { describe, expect, it } from "vitest";
import { adaptRegimes } from "./regimes";

describe("regimesAdapter", () => {
  it("maps UP/DOWN/FLAT to BULL/BEAR/SIDEWAYS without sub-blocks", () => {
    const out = adaptRegimes({
      regimes: [
        { symbol: "BTC", trend: "UP", vol_regime: "HIGH", realized_vol_pct: 2.1, window_bars: 20 },
        { symbol: "ETH", trend: "DOWN", vol_regime: "LOW", realized_vol_pct: 0.1, window_bars: 20 },
        { symbol: "SPX", trend: "FLAT", vol_regime: "NORMAL", realized_vol_pct: 0.8, window_bars: 20 },
      ],
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out.map((r) => r.trend)).toEqual(["BULL", "BEAR", "SIDEWAYS"]);
    expect(out[0].volatility).toBe("HIGH");
    for (const r of out) {
      expect(r.polymarketData).toBeUndefined();
      expect(r.fxData).toBeUndefined();
      expect(r.commodityData).toBeUndefined();
      expect(r.sparkline).toEqual([]);
    }
  });

  it("branches on {available:false}", () => {
    expect(adaptRegimes({ available: false, reason: "e" })).toEqual({ unavailable: "e" });
  });
});
