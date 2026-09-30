import { describe, expect, it } from "vitest";
import { adaptAccounting } from "./accounting";

describe("accountingAdapter", () => {
  it("maps accounts_minor to ledger rows and balanced to a badge", () => {
    const out = adaptAccounting({
      trial_balance_total: 0,
      balanced: true,
      accounts_minor: { "1010": 40220000, "2010": -2200000 },
      open_lot_qty: {},
      tax: {},
      ca_review_queue: [],
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out.balanced).toBe(true);
    expect(out.rows).toHaveLength(2);
    expect(out.rows[0]).toMatchObject({ code: "1010", balanceUsd: 402200 });
    expect(out.rows[0].type).toBe("ASSET");
    expect(out.rows[1].type).toBe("LIABILITY");
  });

  it("branches on {available:false}", () => {
    expect(adaptAccounting({ available: false, reason: "no kernel" })).toEqual({
      unavailable: "no kernel",
    });
  });
});
