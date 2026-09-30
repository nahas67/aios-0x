import { describe, expect, it } from "vitest";
import { adaptAgents } from "./agents";

describe("agentsAdapter", () => {
  it("maps registry agents to AgentNode rows", () => {
    const out = adaptAgents({
      agents: [
        {
          agent_id: "risk",
          community: "c0",
          role: "RISK",
          version: "v1",
          publishes: ["aios.risk.emergency"],
          reputation: 0.9,
        },
      ],
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out[0]).toMatchObject({
      id: "risk",
      name: "risk",
      role: "RISK",
      reputationScore: 0.9,
      status: "ONLINE",
    });
  });

  it("marks reputation-less agents STANDBY and branches on unavailable", () => {
    const out = adaptAgents({
      agents: [
        { agent_id: "x", community: null, role: "weird", version: null, publishes: [], reputation: null },
      ],
    });
    if ("unavailable" in out) throw new Error("unexpected unavailable");
    expect(out[0].status).toBe("STANDBY");
    expect(adaptAgents({ available: false, reason: "t" })).toEqual({ unavailable: "t" });
  });
});
