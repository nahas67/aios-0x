import { describe, expect, it } from "vitest";
import { adaptOpportunities } from "./intelligence";

describe("intelligenceAdapter", () => {
  it("maps opportunities to IntelligenceItems", () => {
    const out = adaptOpportunities({
      opportunities: [
        {
          strategy_id: "s-1",
          symbol: "BTC/USD",
          family: "trend",
          edge_proxy: 0.5,
          expected_rr: 2,
          alpha_decay: null,
          composite_rank: 1,
        },
      ],
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out[0].id).toBe("s-1");
    expect(out[0].headline).toContain("BTC/USD");
  });

  it("branches on {available:false}", () => {
    expect(adaptOpportunities({ available: false, reason: "i" })).toEqual({ unavailable: "i" });
  });
});
