import { describe, expect, it } from "vitest";
import {
  assessClaim,
  mapModelRegistry,
  metricEntries,
  REQUIRED_CLAIM_FIELDS,
  toMetricEntry,
  withEvaluationCount,
  type ModelGovernanceSnapshot,
} from "./modelGovernance";

/**
 * The tests below are mostly about refusal. The view this adapter serves used
 * to render four invented models and a "92.6% AVERAGE" accuracy figure, so the
 * property worth protecting is that absent data stays visibly absent.
 */
describe("mapModelRegistry", () => {
  it("reports absence rather than an empty roster", () => {
    const result = mapModelRegistry({ available: false, models: [] });
    expect(result).toHaveProperty("unavailable");
    // The reason must be the honest one, not a bare "no data".
    expect((result as { unavailable: string }).unavailable).toContain(
      "backend reports absence",
    );
  });

  it("surfaces the server's own reason when it gives one", () => {
    const result = mapModelRegistry({ available: false, reason: "registry offline" });
    expect((result as { unavailable: string }).unavailable).toBe("registry offline");
  });

  it("treats available:true with zero models as absence", () => {
    // Otherwise the view renders an empty page that reads like a populated one.
    const result = mapModelRegistry({ available: true, models: [] });
    expect(result).toHaveProperty("unavailable");
  });

  it("maps a real registry entry without inventing fields", () => {
    const result = mapModelRegistry({
      available: true,
      models: [
        {
          model_id: "m-1",
          version: "3",
          status: "CERTIFIED",
          model_type: "direction",
          artifact_hash: "sha256:abc",
          created_at: "2026-10-01T00:00:00+00:00",
          evaluation_metrics: { accepted_n: 120 },
        },
      ],
    });

    expect(result).toHaveProperty("entries");
    const snapshot = result as ModelGovernanceSnapshot;
    expect(snapshot.entries).toHaveLength(1);
    const entry = snapshot.entries[0];
    expect(entry.id).toBe("m-1@3");
    expect(entry.name).toBe("m-1");
    expect(entry.status).toBe("CERTIFIED");
    expect(entry.artifactHash).toBe("sha256:abc");
  });

  it("leaves absent optional fields null instead of substituting text", () => {
    const result = mapModelRegistry({
      available: true,
      models: [{ model_id: "m-2", version: "1" }],
    });
    const entry = (result as ModelGovernanceSnapshot).entries[0];
    expect(entry.status).toBeNull();
    expect(entry.artifactHash).toBeNull();
    expect(entry.createdAt).toBeNull();
  });
});

describe("assessClaim", () => {
  it("refuses a claim that carries only an accuracy number", () => {
    // This is the exact shape the old view invented: a bare percentage.
    const result = assessClaim({ accuracy: 91.2 });
    expect(result.claimStatus).toBe("NOT_REPORTABLE");
    expect(result.missingClaimFields).toContain("accepted_n");
    expect(result.missingClaimFields).toContain("confidence_interval");
    expect(result.missingClaimFields).toContain("dataset_version");
  });

  it("names every absent companion", () => {
    const result = assessClaim({});
    expect(result.missingClaimFields).toHaveLength(REQUIRED_CLAIM_FIELDS.length);
    expect(result.missingClaimFields).toEqual([...REQUIRED_CLAIM_FIELDS]);
  });

  it("treats an empty string as absent, not as supplied", () => {
    const result = assessClaim({ metric_definition: "   " });
    expect(result.claimStatus).toBe("NOT_REPORTABLE");
    expect(result.missingClaimFields).toContain("metric_definition");
  });

  it("permits presentation only when all fourteen companions are present", () => {
    const complete = Object.fromEntries(REQUIRED_CLAIM_FIELDS.map((f) => [f, "x"]));
    expect(assessClaim(complete).claimStatus).toBe("REPORTABLE");

    const oneShort = { ...complete };
    delete (oneShort as Record<string, unknown>).tail_risk;
    const result = assessClaim(oneShort);
    expect(result.claimStatus).toBe("NOT_REPORTABLE");
    expect(result.missingClaimFields).toEqual(["tail_risk"]);
  });

  it("requires all fourteen, matching the backend gate", () => {
    // Architecture section 11 names the companions; core/claim_gate implements
    // them. If this count drifts, the mirror has drifted from its source.
    expect(REQUIRED_CLAIM_FIELDS).toHaveLength(14);
  });
});

describe("metric rendering", () => {
  it("shows a supplied number as a number", () => {
    expect(toMetricEntry("accepted_n", 120)).toEqual({
      key: "accepted_n",
      display: "120",
      numeric: true,
    });
  });

  it("shows an absent value as unknown rather than coercing it", () => {
    for (const absent of [null, undefined, Number.NaN, { nested: 1 }]) {
      const entry = toMetricEntry("x", absent);
      expect(entry.display).toBe("unknown");
      expect(entry.numeric).toBe(false);
    }
  });

  it("sorts keys so the display order is stable across renders", () => {
    const entries = metricEntries({ zeta: 1, alpha: 2, mid: 3 });
    expect(entries.map((e) => e.key)).toEqual(["alpha", "mid", "zeta"]);
  });
});

describe("withEvaluationCount", () => {
  it("counts real evaluation records", () => {
    const snapshot = mapModelRegistry({
      available: true,
      models: [{ model_id: "m", version: "1" }],
    }) as ModelGovernanceSnapshot;

    const withCount = withEvaluationCount(snapshot, {
      evaluations: [{ evaluation_id: "e1" }, { evaluation_id: "e2" }],
    });
    expect(withCount.evaluationCount).toBe(2);
  });

  it("reports zero when the endpoint returns nothing", () => {
    const snapshot = mapModelRegistry({
      available: true,
      models: [{ model_id: "m", version: "1" }],
    }) as ModelGovernanceSnapshot;

    expect(withEvaluationCount(snapshot, { evaluations: [] }).evaluationCount).toBe(0);
    expect(withEvaluationCount(snapshot, {}).evaluationCount).toBe(0);
  });
});
