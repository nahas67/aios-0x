/**
 * intelligenceAdapter: /api/v1/opportunities → zip IntelligenceItem rows.
 * Confidence/support counts have no source and stay 0; never back-filled.
 */
import type { Opportunity } from "../api/types";
import type { IntelligenceItem } from "../types";
import { type Unavailable } from "./absent";

export function adaptOpportunities(
  payload: { opportunities: Opportunity[] } | { available: false; reason?: string },
): IntelligenceItem[] | Unavailable {
  if ("available" in payload) {
    const reason = payload.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "opportunities unavailable" };
  }
  return payload.opportunities.map((o) => ({
    id: o.strategy_id,
    headline: `${o.family ?? "opportunity"} · ${o.symbol ?? "—"}`,
    detail: `edge ${o.edge_proxy ?? "—"} · expected R:R ${o.expected_rr ?? "—"} · rank ${o.composite_rank ?? "—"}`,
    confidencePct: 0,
    supportAgents: 0,
    counterAgents: 0,
    riskImpact: "MEDIUM",
    action: "WATCH",
    timestamp: "—",
    category: "MACRO",
  }));
}
