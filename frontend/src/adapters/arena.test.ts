import { describe, expect, it } from "vitest";
import { adaptArena, adaptRecommendation, kernelBlocker } from "./arena";
import type { ArenaTrial, ArenaView } from "../api/types";

function side(pnl: number, sideName: string) {
  return {
    side: sideName,
    trades: 30,
    pnl,
    directional_accuracy_pct: 58.1,
    max_drawdown_pct: 4.2,
  };
}

const baseTrial: ArenaTrial = {
  name: "auto:abc12345",
  description: "ml challenger vs baseline",
  metric: "pnl",
  state: "EVALUATED",
  promoted_by: null,
  evaluated_at: "2026-10-02T09:00:00",
  champion: side(120.5, "champion"),
  challenger: side(310.25, "challenger"),
  recommendation: {
    recommendation: "PROMOTE",
    metric: "pnl",
    champion: 120.5,
    challenger: 310.25,
    margin: 189.75,
    note: "Single-window evidence",
  },
  verdict: {
    evaluation_id: "eval-1",
    verdict: "PASS",
    evaluator: "walk_forward",
    summary: "challenger dominates on a held-out window",
    created_at: "2026-10-02T09:00:00",
  },
  notes: ["one window only"],
};

const baseView: ArenaView = {
  wired: true,
  kernel_wired: true,
  trials: [baseTrial],
  note: "single-window evidence",
};

describe("arenaAdapter", () => {
  it("maps a compared trial and keeps the server's own recommendation", () => {
    const out = adaptArena(baseView);
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out.wired).toBe(true);
    expect(out.kernelWired).toBe(true);
    expect(out.trials).toHaveLength(1);
    const trial = out.trials[0];
    expect(trial.name).toBe("auto:abc12345");
    expect(trial.recommendation.recommendation).toBe("PROMOTE");
    expect(trial.recommendation.margin).toBeCloseTo(189.75);
    expect(trial.recommendation.insufficientEvidence).toBe(false);
    expect(trial.champion?.pnl).toBeCloseTo(120.5);
    expect(trial.notes).toEqual(["one window only"]);
  });

  // THE POINT OF THE ADAPTER. wired:false arrives with trials:[] and a note that says
  // so. Returning Unavailable here would claim nobody could read the arena; returning an
  // empty trial list would claim the operator asked and was told there are none. Both
  // are untrue, and the server read the endpoint fine.
  it("keeps wired:false as a wiring fact rather than absence or emptiness", () => {
    const out = adaptArena({
      wired: false,
      kernel_wired: false,
      trials: [],
      note: "No ChallengeRegistry is attached to this composition root.",
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out.wired).toBe(false);
    expect(out.trials).toEqual([]);
    expect(out.note).toContain("composition root");
  });

  it("distinguishes an unwired arena from a wired arena holding zero trials", () => {
    const unwired = adaptArena({ wired: false, kernel_wired: false, trials: [], note: "n" });
    const wiredEmpty = adaptArena({ wired: true, kernel_wired: true, trials: [], note: "n" });
    expect("unavailable" in unwired || "unavailable" in wiredEmpty).toBe(false);
    if ("unavailable" in unwired || "unavailable" in wiredEmpty) return;
    expect(unwired.wired).toBe(false);
    expect(wiredEmpty.wired).toBe(true);
    expect(unwired.trials.length).toBe(wiredEmpty.trials.length);
  });

  // core/challenger.py returns {"recommendation": "INSUFFICIENT_EVIDENCE"} with no other
  // key. Rendering it as a number or a loss is the defect this guards.
  it("nulls every comparison figure when the server says INSUFFICIENT_EVIDENCE", () => {
    const out = adaptArena({
      ...baseView,
      trials: [
        {
          ...baseTrial,
          state: "PROPOSED",
          champion: null,
          challenger: null,
          evaluated_at: null,
          verdict: null,
          recommendation: { recommendation: "INSUFFICIENT_EVIDENCE" },
        },
      ],
    });
    if ("unavailable" in out) return;
    const rec = out.trials[0].recommendation;
    expect(rec.recommendation).toBe("INSUFFICIENT_EVIDENCE");
    expect(rec.insufficientEvidence).toBe(true);
    expect(rec.champion).toBeNull();
    expect(rec.challenger).toBeNull();
    expect(rec.margin).toBeNull();
    expect(rec.metric).toBeNull();
  });

  it("drops comparison figures rather than deriving them from the two sides", () => {
    // The per-side results ARE present here, so a client-side re-derivation would be
    // possible — which is exactly why the adapter must not do it. Doing so would give
    // the console its own recommendation.
    const rec = adaptRecommendation({
      recommendation: "INSUFFICIENT_EVIDENCE",
    });
    expect(rec.margin).toBeNull();
  });

  it("marks promotion reachable only when a PASS verdict exists", () => {
    const out = adaptArena(baseView);
    if ("unavailable" in out) return;
    expect(out.trials[0].promotionPreconditionsMet).toBe(true);
    expect(out.trials[0].promotionBlockedReason).toBeNull();
  });

  it("names the missing EvaluationRecord as the blocker", () => {
    const out = adaptArena({ ...baseView, trials: [{ ...baseTrial, verdict: null }] });
    if ("unavailable" in out) return;
    expect(out.trials[0].promotionPreconditionsMet).toBe(false);
    expect(out.trials[0].promotionBlockedReason).toContain("EvaluationRecord");
  });

  it("refuses promotion on a non-PASS verdict", () => {
    const out = adaptArena({
      ...baseView,
      trials: [
        {
          ...baseTrial,
          verdict: { ...baseTrial.verdict!, verdict: "FAIL" },
        },
      ],
    });
    if ("unavailable" in out) return;
    expect(out.trials[0].promotionPreconditionsMet).toBe(false);
    expect(out.trials[0].promotionBlockedReason).toContain("FAIL");
  });

  it("offers no reversal for a PROMOTED trial", () => {
    const out = adaptArena({
      ...baseView,
      trials: [{ ...baseTrial, state: "PROMOTED", promoted_by: "operator-7" }],
    });
    if ("unavailable" in out) return;
    expect(out.trials[0].promotionPreconditionsMet).toBe(false);
    expect(out.trials[0].promotionBlockedReason).toContain("irreversible");
  });

  it("treats a REJECTED trial as terminal", () => {
    const out = adaptArena({ ...baseView, trials: [{ ...baseTrial, state: "REJECTED" }] });
    if ("unavailable" in out) return;
    expect(out.trials[0].promotionPreconditionsMet).toBe(false);
  });

  it("reports an unreadable payload as unavailable rather than as an empty arena", () => {
    const out = adaptArena({ wired: true, kernel_wired: true } as unknown as ArenaView);
    expect("unavailable" in out).toBe(true);
  });

  it("turns a missing side into null, never into a zero result", () => {
    const out = adaptArena({ ...baseView, trials: [{ ...baseTrial, challenger: null }] });
    if ("unavailable" in out) return;
    expect(out.trials[0].challenger).toBeNull();
    expect(out.trials[0].champion).not.toBeNull();
  });

  it("keeps kernel_wired false visible as a promotion refusal reason", () => {
    expect(kernelBlocker(true)).toBeNull();
    expect(kernelBlocker(false)).toContain("will be refused");
  });

  it("substitutes an honest note when the server sends none", () => {
    const out = adaptArena({ ...baseView, note: "" });
    if ("unavailable" in out) return;
    expect(out.note).toContain("not a statement about the arena");
  });
});