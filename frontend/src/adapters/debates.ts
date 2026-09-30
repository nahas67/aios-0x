/**
 * debatesAdapter: /api/v1/debates → debate sessions for the feed.
 *
 * Backend: {available:true, debates:[{id, symbol, side, status,
 *            consensusScorePct, turns:[{agentId, stance, thesis,
 *            confidencePct}]}]} or {available:false, reason}.
 * Key renames only — nothing is invented beyond documented nulls.
 */
import type { DebatesView, DebateTurnWire } from "../api/types";
import { type Unavailable } from "./absent";

export interface DebateTurnView {
  agentId: string;
  stance: string;
  thesis: string;
  confidencePct: number | null;
}

export interface DebateSessionView {
  id: string;
  symbol: string | null;
  side: string;
  status: string;
  consensusScorePct: number | null;
  turns: DebateTurnView[];
}

function adaptTurn(t: DebateTurnWire): DebateTurnView {
  return {
    agentId: t.agentId ?? "UNKNOWN",
    stance: t.stance ?? "UNKNOWN",
    thesis: t.thesis ?? "",
    confidencePct: t.confidencePct ?? null,
  };
}

export function adaptDebates(payload: DebatesView): DebateSessionView[] | Unavailable {
  if (payload.available === false) {
    const reason = payload.reason;
    return {
      unavailable:
        typeof reason === "string" && reason.length > 0 ? reason : "no debates recorded",
    };
  }
  return payload.debates.map((d) => ({
    id: d.id ?? "unknown",
    symbol: d.symbol ?? null,
    side: d.side ?? "NEUTRAL",
    status: d.status ?? "UNKNOWN",
    consensusScorePct: d.consensusScorePct ?? null,
    turns: Array.isArray(d.turns) ? d.turns.map(adaptTurn) : [],
  }));
}
