/**
 * researchAdapter: /knowledge + /research + /memory → research workspace.
 *
 * Hypotheses come from the knowledge `recent` list; calibration from the
 * research report; memory is an opaque record surfaced only as scalar
 * annotations when present. Anything absent renders as "—".
 */
import type { CalibrationReport, KnowledgeSummary } from "../api/types";

export interface HypothesisView {
  id: string;
  statement: string;
  symbol: string | null;
  status: string;
  confidence: number | null;
  evidenceTotal: number;
  supports: number;
  contradicts: number;
  lastUpdated: string;
}

export interface CalibrationView {
  reportId: string;
  totalScored: number;
  brierScore: number;
  directionalAccuracyPct: number;
  reliable: boolean;
}

export interface AdaptedResearch {
  knowledgeAvailable: boolean;
  knowledgeTotal: number | null;
  byStatus: Record<string, number>;
  hypotheses: HypothesisView[];
  calibration: CalibrationView | null;
  memoryScalars: Record<string, string>;
}

function scalarsOf(record: Record<string, unknown> | null | undefined): Record<string, string> {
  if (!record || typeof record !== "object") return {};
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(record)) {
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      out[k] = String(v);
    }
  }
  return out;
}

export function adaptResearch(
  knowledge: KnowledgeSummary | { available: false } | null,
  report: CalibrationReport | null,
  memory: Record<string, unknown> | { available: false } | null,
): AdaptedResearch {
  const kAvailable = knowledge != null && (knowledge as KnowledgeSummary).available === true;
  const k = (kAvailable ? knowledge : null) as KnowledgeSummary | null;
  return {
    knowledgeAvailable: kAvailable,
    knowledgeTotal: k?.total ?? null,
    byStatus: k?.by_status ?? {},
    hypotheses: (k?.recent ?? []).map((r) => ({
      id: r.hypothesis_id,
      statement: r.statement,
      symbol: r.symbol,
      status: r.status,
      confidence: r.confidence,
      evidenceTotal: r.evidence_total,
      supports: r.supports,
      contradicts: r.contradicts,
      lastUpdated: r.last_updated,
    })),
    calibration: report
      ? {
          reportId: report.report_id,
          totalScored: report.total_scored,
          brierScore: report.brier_score,
          directionalAccuracyPct: report.directional_accuracy_pct,
          reliable: report.reliable,
        }
      : null,
    memoryScalars: scalarsOf(
      memory && !("available" in (memory as object)) ? (memory as Record<string, unknown>) : null,
    ),
  };
}
