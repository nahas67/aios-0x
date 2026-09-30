import { describe, expect, it } from "vitest";
import { adaptPositions } from "./positions";
import type { Position } from "../api/types";

const row: Position = {
  execution_id: "exec-1",
  symbol: "BTC/USD",
  action: "BUY",
  qty: 2,
  entry: 60000,
  mark: 66000,
  unrealized: 12000,
  stop: 55000,
  target: 75000,
  mark_value: 132000,
  asset_class: "CRYPTO",
};

describe("positionsAdapter", () => {
  it("renames backend fields to the zip Position", () => {
    const out = adaptPositions({ positions: [row] });
    expect("unavailable" in out).toBe(false);
    const [p] = out as import("../types").Position[];
    expect(p.id).toBe("exec-1");
    expect(p.side).toBe("LONG");
    expect(p.size).toBe(2);
    expect(p.entryPrice).toBe(60000);
    expect(p.markPrice).toBe(66000);
    expect(p.unrealizedPnlUsd).toBe(12000);
    expect(p.unrealizedPnlPct).toBeCloseTo(10, 5);
    expect(p.stopLossPrice).toBe(55000);
    expect(p.takeProfitPrice).toBe(75000);
  });

  it("maps SELL to SHORT and null stop/target to undefined", () => {
    const out = adaptPositions({
      positions: [{ ...row, execution_id: "e2", action: "SELL", stop: null, target: null }],
    }) as import("../types").Position[];
    expect(out[0].side).toBe("SHORT");
    expect(out[0].stopLossPrice).toBeUndefined();
    expect(out[0].takeProfitPrice).toBeUndefined();
  });

  it("branches on {available:false}", () => {
    expect(adaptPositions({ available: false, reason: "down" })).toEqual({
      unavailable: "down",
    });
  });
});
