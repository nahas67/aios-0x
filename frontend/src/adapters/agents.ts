/**
 * agentsAdapter: /api/v1/agents roster → zip AgentNode rows.
 * Reputation/confidence/accuracy/latency beyond `reputation` are not
 * published; unknowns stay neutral (0 / "—" / STANDBY).
 */
import type { Agent } from "../api/types";
import type { AgentNode, AgentRole } from "../types";
import { type Unavailable } from "./absent";

function toRole(raw: string | null): AgentRole {
  const r = (raw ?? "").toUpperCase();
  if (r.includes("POLYMARKET")) return "POLYMARKET_ARB";
  if (r.includes("COMMODITY")) return "COMMODITY_SPECIALIST";
  if (r.includes("CROSS_BORDER")) return "CROSS_BORDER_EQUITIES";
  if (r.includes("GLOBAL_MACRO") || (r.includes("MACRO") && r.includes("FX"))) return "GLOBAL_MACRO_FX";
  if (r.includes("MACRO")) return "MACRO";
  if (r.includes("TECHNICAL")) return "TECHNICAL";
  if (r.includes("FUNDAMENTAL")) return "FUNDAMENTAL";
  if (r.includes("SENTIMENT")) return "SENTIMENT";
  if (r.includes("RISK")) return "RISK";
  if (r.includes("EXECUTION")) return "EXECUTION";
  if (r.includes("CHALLENGER")) return "CHALLENGER";
  return "VERIFIER";
}

export function adaptAgents(
  payload: { agents: Agent[] } | { available: false; reason?: string },
): AgentNode[] | Unavailable {
  if ("available" in payload) {
    const reason = payload.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "agent roster unavailable" };
  }
  return payload.agents.map((a) => ({
    id: a.agent_id,
    name: a.agent_id,
    role: toRole(a.role),
    reputationScore: a.reputation ?? 0.5,
    confidencePct: 0,
    currentThesis:
      a.publishes.length > 0 ? `publishes: ${a.publishes.join(", ")}` : (a.community ?? "—"),
    bias: "NEUTRAL",
    recentAccuracyPct: 0,
    status: a.reputation != null ? "ONLINE" : "STANDBY",
    lastEvaluated: "—",
    latencyMs: 0,
    modelsUsed: a.version ? [a.version] : [],
  }));
}
