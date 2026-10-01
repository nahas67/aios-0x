/**
 * Model-governance adapter: registry rows and evaluation records, honestly.
 *
 * This adapter exists because the view it serves used to invent its entire
 * contents. It rendered four named models, weights hashes, accuracy figures,
 * latencies and evaluation dates that no backend call had produced, and it
 * presented "BENCHMARK ACCURACY: 92.6% AVERAGE" as a result. That is a direct
 * violation of three separate rules this repository holds itself to:
 *
 *   - architecture section 11 (Statistical Claim Gate): a performance claim
 *     "must be rejected unless accompanied by" fourteen named companions;
 *   - core/claim_gate.py, which is the implementation of that rule and which
 *     describes a caller with no provenance as receiving a NOT REPORTABLE
 *     response with the missing fields named;
 *   - CONSTITUTION.md section 3, Honesty Law 1: never fabricate capability.
 *
 * The backend was already honest about this. `views.models_registry_view`
 * returns `{available: false, models: []}` when there is no registry, and its
 * docstring says so: "never a fabricated roster". The fiction was entirely
 * client-side, which is the more expensive kind: a server that lies can be
 * checked, and a client that lies looks exactly like a working feature.
 *
 * So the rule lives here once and is asserted against the backend's own list.
 * REQUIRED_CLAIM_FIELDS is a mirror of `core.claim_gate.REQUIRED_CLAIM_FIELDS`.
 * If the backend's list changes, this mirror is wrong -- and that is the point
 * at which the drift becomes visible rather than silent.
 */
import { isUnavailable, unavailableReason, type Unavailable } from "./absent";

/** Mirror of `core.claim_gate.REQUIRED_CLAIM_FIELDS`, same order, same names. */
export const REQUIRED_CLAIM_FIELDS: readonly string[] = [
  "metric_definition",
  "accepted_n",
  "coverage",
  "time_period",
  "asset_universe",
  "regime_coverage",
  "net_of_cost",
  "out_of_sample",
  "confidence_interval",
  "max_drawdown",
  "tail_risk",
  "experiment_count",
  "model_version",
  "dataset_version",
];

/** One declared metric, rendered as given. Never interpreted or summarised. */
export interface MetricEntry {
  key: string;
  /** null when the backend sent nothing usable -- renders as "unknown". */
  display: string;
  /** True only when the backend supplied a finite number. */
  numeric: boolean;
}

export type ClaimStatus = "REPORTABLE" | "NOT_REPORTABLE";

export interface ModelGovernanceEntry {
  id: string;
  name: string;
  version: string;
  status: string | null;
  modelType: string | null;
  artifactHash: string | null;
  createdAt: string | null;
  metrics: MetricEntry[];
  walkForward: MetricEntry[];
  claimStatus: ClaimStatus;
  /** Which companions are absent. Empty exactly when claimStatus is REPORTABLE. */
  missingClaimFields: string[];
}

export interface ModelGovernanceSnapshot {
  entries: ModelGovernanceEntry[];
  /** Real record count from the evaluations endpoint. 0 is a legitimate answer. */
  evaluationCount: number;
}

const FALLBACK =
  "No model registry is wired on this deployment. The backend reports absence " +
  "rather than an empty roster, so there is nothing to show and nothing to " +
  "estimate. An earlier version of this view invented four models and a " +
  "92.6% average accuracy here.";

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asText(value: unknown): string | null {
  if (typeof value === "string") return value.length > 0 ? value : null;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

/** Render one declared metric without inventing precision it may not have. */
export function toMetricEntry(key: string, value: unknown): MetricEntry {
  if (typeof value === "number" && Number.isFinite(value)) {
    return { key, display: String(value), numeric: true };
  }
  if (typeof value === "boolean") {
    return { key, display: value ? "true" : "false", numeric: false };
  }
  if (typeof value === "string" && value.length > 0) {
    return { key, display: value, numeric: false };
  }
  // null / undefined / NaN / nested object: shown as unknown rather than
  // coerced into something that would read as a measurement.
  return { key, display: "unknown", numeric: false };
}

export function metricEntries(source: unknown): MetricEntry[] {
  const record = asRecord(source);
  return Object.keys(record)
    .sort()
    .map((key) => toMetricEntry(key, record[key]));
}

/**
 * Apply the claim gate. A performance claim may only be presented with all
 * fourteen companions; otherwise it is NOT REPORTABLE and the absent ones are
 * named. This mirrors `core.claim_gate` rather than re-deciding the rule.
 */
export function assessClaim(metrics: unknown): {
  claimStatus: ClaimStatus;
  missingClaimFields: string[];
} {
  const record = asRecord(metrics);
  const missing = REQUIRED_CLAIM_FIELDS.filter((field) => {
    const value = record[field];
    if (value === undefined || value === null) return true;
    if (typeof value === "string") return value.trim().length === 0;
    return false;
  });
  return {
    claimStatus: missing.length === 0 ? "REPORTABLE" : "NOT_REPORTABLE",
    missingClaimFields: missing,
  };
}

/**
 * Map `/api/v1/models/registry`.
 *
 * `{available: false}` is an answer, not an error, and it is the answer this
 * view most often gets on a fresh deployment. It is passed through as
 * `Unavailable` so the caller renders the reason rather than a placeholder
 * roster.
 */
export function mapModelRegistry(
  payload: unknown,
): ModelGovernanceSnapshot | Unavailable {
  if (isUnavailable(payload)) {
    return { unavailable: unavailableReason(payload, FALLBACK) };
  }

  const record = asRecord(payload);
  const rawModels = Array.isArray(record.models) ? record.models : [];

  const entries = rawModels.map((raw) => {
    const model = asRecord(raw);
    const metrics = model.evaluation_metrics;
    const { claimStatus, missingClaimFields } = assessClaim(metrics);
    const modelId = asText(model.model_id);
    const version = asText(model.version) ?? "";
    return {
      id: asText(model.id) ?? (modelId ? `${modelId}@${version}` : version || "unknown"),
      name: modelId ?? version ?? "unknown",
      version,
      status: asText(model.status),
      modelType: asText(model.model_type),
      artifactHash: asText(model.artifact_hash),
      createdAt: asText(model.created_at),
      metrics: metricEntries(metrics),
      walkForward: metricEntries(model.walk_forward),
      claimStatus,
      missingClaimFields,
    } satisfies ModelGovernanceEntry;
  });

  // `available: true` with an empty roster is still absence, and saying
  // otherwise would render an empty page that reads like a populated one.
  if (entries.length === 0) {
    return { unavailable: FALLBACK };
  }

  return { entries, evaluationCount: 0 };
}

/** Fold the real evaluation count in. Never estimated. */
export function withEvaluationCount(
  snapshot: ModelGovernanceSnapshot,
  payload: unknown,
): ModelGovernanceSnapshot {
  const record = asRecord(payload);
  const evaluations = Array.isArray(record.evaluations) ? record.evaluations : [];
  return { ...snapshot, evaluationCount: evaluations.length };
}
