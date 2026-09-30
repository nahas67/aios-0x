import { describe, expect, it } from "vitest";
import { adaptDecisionDrilldown, adaptExecutionRowToTrace } from "./executions";

describe("executionsAdapter", () => {
  it("maps a decision drilldown to a ProvenanceTrace", () => {
    const out = adaptDecisionDrilldown({
      execution_id: "exec-9",
      decision: { action: "BUY", symbol: "BTC/USD", family: "trend", position_size_pct: 5 },
      reason: { thesis: "breakout" },
      evidence: { supporting_arguments: ["a"], counter_arguments: ["b"] },
      verification: {
        confidence_score: 0.8,
        fact_score: null,
        balance_score: null,
        math_score: null,
        flagged_hallucinations: [],
      },
      risk: { stop_loss_price: 1, take_profit_price: 2 },
      outcome: { actual_pnl: null, exit_reason: null, direction_correct: null, lessons_learned: [] },
      chain_complete: true,
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out.executionId).toBe("exec-9");
    expect(out.symbol).toBe("BTC/USD");
    expect(out.side).toBe("BUY");
    expect(out.decision.consensusScore).toBe(0.8);
  });

  it("maps an execution row to an honest stub trace", () => {
    const out = adaptExecutionRowToTrace({
      execution_id: "exec-1",
      symbol: "ETH/USD",
      fill_price: 3500,
      realized_pnl: 12,
      action: "SELL",
      confidence_pct: null,
      exit_reason: "target",
    });
    if ("unavailable" in out) throw new Error("unexpected unavailable");
    expect(out.side).toBe("SELL");
    expect(out.fillPrice).toBe(3500);
  });

  it("branches on {available:false}", () => {
    expect(
      adaptDecisionDrilldown({ available: false, reason: "u" } as unknown as import("../api/types").DecisionDrilldown),
    ).toEqual({ unavailable: "u" });
  });
});
