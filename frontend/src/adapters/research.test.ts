import { describe, expect, it } from "vitest";
import { adaptResearch } from "./research";

describe("researchAdapter", () => {
  it("lists hypotheses from /knowledge recent and calibration from /research", () => {
    const out = adaptResearch(
      {
        available: true,
        total: 2,
        by_status: { TESTING: 2 },
        recent: [
          {
            hypothesis_id: "h1",
            statement: "BTC trends up",
            symbol: "BTC/USD",
            status: "TESTING",
            confidence: 0.7,
            evidence_total: 3,
            supports: 2,
            contradicts: 1,
            outcomes: 0,
            last_updated: "2026-09-30",
          },
        ],
      },
      {
        report_id: "r1",
        created_at: "2026-09-30",
        total_scored: 40,
        brier_score: 0.21,
        directional_accuracy_pct: 62.5,
        buckets: [],
        reliable: true,
      },
      { available: false },
    );
    expect(out.hypotheses).toHaveLength(1);
    expect(out.hypotheses[0]).toMatchObject({ id: "h1", status: "TESTING", supports: 2 });
    expect(out.calibration).toMatchObject({ totalScored: 40, brierScore: 0.21 });
    expect(out.knowledgeTotal).toBe(2);
  });

  it("marks knowledge unavailable instead of fabricating hypotheses", () => {
    const out = adaptResearch({ available: false }, null, null);
    expect(out.hypotheses).toEqual([]);
    expect(out.knowledgeAvailable).toBe(false);
    expect(out.calibration).toBeNull();
  });
});
