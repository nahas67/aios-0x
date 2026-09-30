import { describe, expect, it } from "vitest";
import { adaptMarketCandles } from "./market";

describe("marketAdapter", () => {
  it("passes real bars and nullable server indicators through untouched", () => {
    const out = adaptMarketCandles({
      available: true,
      symbol: "BTC/USD",
      tf: "15m",
      candles: [
        { time: "2026-09-30T00:00:00+00:00", open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
      ],
      indicators: { ema20: null, ema50: null, rsi14: 55.2, macd: null, bollinger: null },
      source: "sim",
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out.symbol).toBe("BTC/USD");
    expect(out.bars).toHaveLength(1);
    expect(out.bars[0]).toMatchObject({ open: 1, close: 1.5, volume: 10 });
    // Null indicators stay null — the view renders "—", never invents.
    expect(out.indicators.ema20).toBeNull();
    expect(out.indicators.rsi14).toBe(55.2);
  });

  it("branches on {available:false} with the server reason", () => {
    expect(adaptMarketCandles({ available: false, reason: "no market fetcher wired" })).toEqual({
      unavailable: "no market fetcher wired",
    });
  });
});
