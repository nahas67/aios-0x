import { describe, expect, it } from "vitest";
import { adaptDebates } from "./debates";

describe("debatesAdapter", () => {
  it("renames wire turns without inventing fields", () => {
    const out = adaptDebates({
      available: true,
      debates: [
        {
          id: "d1",
          symbol: "BTC/USD",
          side: "LONG",
          status: "ACTIVE_DELIBERATING",
          consensusScorePct: 61.5,
          turns: [
            { agentId: "macro", stance: "PROPOSE_LONG", thesis: "up", confidencePct: 80 },
            { agentId: "risk", stance: "CHALLENGE_RISK", thesis: "careful", confidencePct: null },
          ],
        },
      ],
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ id: "d1", symbol: "BTC/USD", consensusScorePct: 61.5 });
    expect(out[0].turns).toHaveLength(2);
    expect(out[0].turns[1].confidencePct).toBeNull();
  });

  it("branches on {available:false} with the server reason", () => {
    expect(
      adaptDebates({ available: false, reason: "no debates recorded (MODEL_PROVIDER=none)" }),
    ).toEqual({ unavailable: "no debates recorded (MODEL_PROVIDER=none)" });
  });

  it("defaults a missing reason to honest-absence text", () => {
    expect(adaptDebates({ available: false, reason: "" })).toEqual({
      unavailable: "no debates recorded",
    });
  });
});
