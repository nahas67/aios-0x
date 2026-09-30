/**
 * executionsAdapter: /api/v1/executions rows + /api/v1/decisions/{id}
 * drill-downs → zip ProvenanceTrace rows.
 *
 * Fields with no source (quantity, slippage, hashes, venue strategy) stay
 * at honest zero/placeholder values; nothing is back-filled.
 */
import type { DecisionDrilldown, Execution } from "../api/types";
import type { ProvenanceTrace } from "../types";
import { type Unavailable } from "./absent";

function stubTrace(executionId: string, symbol: string, side: "BUY" | "SELL"): ProvenanceTrace {
  return {
    executionId,
    symbol,
    side,
    quantity: 0,
    fillPrice: 0,
    timestamp: "—",
    slippageBps: 0,
    decision: {
      decisionId: executionId,
      rationale: "—",
      consensusScore: 0,
      decisionAgent: "—",
      riskCheckPassed: false,
      firewallDigest: "—",
    },
    strategy: {
      strategyId: "—",
      name: "—",
      family: "—",
      targetSharpe: 0,
      allocatedCapitalUsd: 0,
    },
    hypothesis: {
      hypothesisId: "—",
      title: "—",
      formalStatement: "—",
      verificationStatus: "TESTING",
    },
    evidence: { evidenceId: "—", claims: [], counterClaims: [], confidence: 0 },
    source: {
      sourceType: "EVENT_LOG",
      feed: `/api/v1/decisions/${executionId}`,
      rawPayloadHash: "—",
      signatureVerified: false,
    },
    integrityHash: "—",
  };
}

/** Lightweight row for lists; full lineage loads on demand via drill-down. */
export function adaptExecutionRowToTrace(
  e: Execution | { available: false; reason?: string },
): ProvenanceTrace | Unavailable {
  if ("available" in e) {
    const reason = e.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "execution unavailable" };
  }
  const trace = stubTrace(e.execution_id, e.symbol ?? "—", e.action === "SELL" ? "SELL" : "BUY");
  trace.fillPrice = e.fill_price ?? 0;
  trace.decision.consensusScore = e.confidence_pct ?? 0;
  return trace;
}

export function adaptDecisionDrilldown(
  d: DecisionDrilldown | { available: false; reason?: string },
  exec?: Execution,
): ProvenanceTrace | Unavailable {
  if ("available" in d) {
    const reason = d.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "decision unavailable" };
  }
  const side = d.decision.action === "SELL" ? "SELL" : "BUY";
  const trace = stubTrace(d.execution_id, d.decision.symbol ?? exec?.symbol ?? "—", side);
  trace.fillPrice = exec?.fill_price ?? 0;
  trace.decision = {
    decisionId: d.execution_id,
    rationale: d.reason.thesis ?? "—",
    consensusScore: d.verification.confidence_score ?? 0,
    decisionAgent: "—",
    riskCheckPassed: d.chain_complete,
    firewallDigest: "—",
  };
  trace.strategy = {
    strategyId: "—",
    name: d.decision.family ?? "—",
    family: d.decision.family ?? "—",
    targetSharpe: 0,
    allocatedCapitalUsd: 0,
  };
  trace.hypothesis = {
    hypothesisId: "—",
    title: d.reason.thesis ?? "—",
    formalStatement: d.reason.thesis ?? "—",
    verificationStatus: "TESTING",
  };
  trace.evidence = {
    evidenceId: "—",
    claims: d.evidence.supporting_arguments,
    counterClaims: d.evidence.counter_arguments,
    confidence: d.verification.confidence_score ?? 0,
  };
  return trace;
}
