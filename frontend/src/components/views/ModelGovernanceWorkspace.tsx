/**
 * Model governance: the registry as it actually is.
 *
 * This view previously invented its entire contents -- four named models,
 * weights hashes, accuracy figures, latencies, context lengths, evaluation
 * dates, a system prompt hash, a sampling temperature, and a "92.6% AVERAGE"
 * benchmark accuracy. None of it came from a backend call. The API it needed
 * (`modelsApi`, `evaluationsApi`) existed, was typed, and was served on two
 * routes; it was simply never called.
 *
 * That mattered more than a cosmetic bug. Architecture section 11 requires a
 * performance claim to be rejected unless it carries fourteen named
 * companions, `core/claim_gate.py` implements exactly that, and
 * CONSTITUTION.md section 3 forbids fabricating capability. A rendered number is
 * not evidence, and this view was rendering numbers the system could not
 * justify -- which `docs/DEPENDENCY_POLICY.md` names as a refused pattern in
 * its own words.
 *
 * The backend already had the honest answer: `models_registry_view` returns
 * `{available: false, models: []}` when no registry is wired, documented as
 * "never a fabricated roster". So the correct behaviour on an unwired
 * deployment is to say so, and that is what this view does.
 */
import React, { useMemo, useState } from "react";
import { Binary, ShieldCheck, CheckCircle2, CircleSlash } from "lucide-react";

import { modelsApi } from "../../api/backend";
import type { RegistryModel, EvaluationRecord } from "../../api/types";
import { useApi } from "../../hooks/useApi";
import { Unavailable } from "../Unavailable";
import {
  mapModelRegistry,
  withEvaluationCount,
  type ModelGovernanceEntry,
  type MetricEntry,
} from "../../adapters/modelGovernance";

const LIFECYCLE_STAGES = [
  "INIT",
  "TRAIN",
  "EVALUATE",
  "PROMOTE",
  "DEPLOY",
  "MONITOR",
  "REPUTATION",
  "RETIRE",
] as const;

function MetricRow({ entry }: { entry: MetricEntry }) {
  return (
    <div className="flex items-center justify-between gap-3 text-[10px]">
      <span className="text-slate-500 truncate">{entry.key}</span>
      <span
        className={
          entry.numeric
            ? "text-slate-200 font-mono-num font-bold"
            : "text-slate-500 italic"
        }
      >
        {entry.display}
      </span>
    </div>
  );
}

function EntryInspector({ entry }: { entry: ModelGovernanceEntry }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
        <div>
          <div className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold">
            REGISTRY RECORD
          </div>
          <h3 className="text-base font-bold text-white mt-0.5 break-all">{entry.id}</h3>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded bg-white/[0.04] text-slate-300 border border-white/[0.10] font-bold shrink-0">
          {entry.status ?? "STATUS UNKNOWN"}
        </span>
      </div>

      <div className="space-y-2 text-xs">
        <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between gap-3">
          <span className="text-slate-400 shrink-0">MODEL ID:</span>
          <span className="text-slate-200 font-mono text-[11px] truncate">{entry.name}</span>
        </div>
        <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between gap-3">
          <span className="text-slate-400 shrink-0">VERSION:</span>
          <span className="text-slate-200 font-mono text-[11px]">
            {entry.version || "unknown"}
          </span>
        </div>
        <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between gap-3">
          <span className="text-slate-400 shrink-0">MODEL TYPE:</span>
          <span className="text-slate-200 font-mono text-[11px]">
            {entry.modelType ?? "unknown"}
          </span>
        </div>
        <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between gap-3">
          <span className="text-slate-400 shrink-0">ARTIFACT HASH:</span>
          <span className="text-cyan-300 font-mono select-all text-[11px] break-all">
            {entry.artifactHash ?? "not recorded"}
          </span>
        </div>
        <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between gap-3">
          <span className="text-slate-400 shrink-0">REGISTERED AT:</span>
          <span className="text-slate-200 font-mono text-[11px]">
            {entry.createdAt ?? "not recorded"}
          </span>
        </div>
      </div>

      <div>
        <div className="text-[10px] text-slate-400 uppercase tracking-widest font-bold mb-1.5">
          DECLARED EVALUATION METRICS
        </div>
        {entry.metrics.length === 0 ? (
          <div className="text-[10px] text-slate-500 italic">
            No metrics recorded for this version.
          </div>
        ) : (
          <div className="space-y-1">
            {entry.metrics.map((m) => (
              <MetricRow key={m.key} entry={m} />
            ))}
          </div>
        )}
      </div>

      {entry.walkForward.length > 0 && (
        <div>
          <div className="text-[10px] text-slate-400 uppercase tracking-widest font-bold mb-1.5">
            WALK-FORWARD
          </div>
          <div className="space-y-1">
            {entry.walkForward.map((m) => (
              <MetricRow key={m.key} entry={m} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export const ModelGovernanceWorkspace: React.FC = () => {
  const registry = useApi<{
    available: boolean;
    models: RegistryModel[];
    reason?: string;
  }>(modelsApi.registry);
  const evaluations = useApi<{ evaluations: EvaluationRecord[] }>(
    modelsApi.evaluations,
  );  const [selectedId, setSelectedId] = useState<string | null>(null);

  const snapshot = useMemo(() => {
    if (registry.loading) return { state: "loading" as const };
    if (registry.error) return { state: "error" as const, reason: registry.error };
    const mapped = mapModelRegistry(registry.data);
    if ("unavailable" in mapped) {
      return { state: "absent" as const, reason: mapped.unavailable };
    }
    const withCount =
      evaluations.data !== null && !evaluations.error
        ? withEvaluationCount(mapped, evaluations.data)
        : mapped;
    return { state: "ready" as const, snapshot: withCount };
  }, [registry.loading, registry.error, registry.data, evaluations.data, evaluations.error]);

  if (snapshot.state === "loading") {
    return (
      <div className="pb-12 font-mono text-xs text-slate-500 p-4">
        Reading the model registry...
      </div>
    );
  }

  if (snapshot.state === "error") {
    return (
      <div className="pb-12 font-mono">
        <Unavailable
          title="Registry unreadable"
          reason={`The model registry could not be read: ${snapshot.reason}. No figures are shown, because a registry that cannot be read cannot be summarised.`}
        />
      </div>
    );
  }

  if (snapshot.state === "absent") {
    return (
      <div className="pb-12 font-mono space-y-4">
        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 flex items-center gap-2">
          <Binary className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
            MODEL GOVERNANCE
          </h2>
        </div>
        <Unavailable title="No model registry" reason={snapshot.reason} />
      </div>
    );
  }

  const { entries, evaluationCount } = snapshot.snapshot;
  const active = entries.find((e) => e.id === selectedId) ?? entries[0];
  const reportable = entries.filter((e) => e.claimStatus === "REPORTABLE").length;

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Binary className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              MODEL GOVERNANCE
            </h2>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Model registry &middot; evaluation records &middot; claim-gated reporting
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">REGISTERED VERSIONS:</span>{" "}
            <span className="text-emerald-400 font-bold">{entries.length}</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">EVALUATION RECORDS:</span>{" "}
            <span className="text-cyan-300 font-bold">{evaluationCount}</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">REPORTABLE CLAIMS:</span>{" "}
            <span className={reportable > 0 ? "text-emerald-400 font-bold" : "text-amber-300 font-bold"}>
              {reportable} / {entries.length}
            </span>
          </div>
        </div>
      </div>

      {/* Lifecycle vocabulary, not lifecycle state.
          The registry does not report per-stage progress, so no stage is marked
          passed. Marking all eight "PASSED" is exactly the fiction this view
          used to render, and a stage list with no state beside it is honest. */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold mb-3">
          LIFECYCLE VOCABULARY
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {LIFECYCLE_STAGES.map((stage) => (
            <div
              key={stage}
              className="p-2 rounded bg-white/[0.02] border border-white/[0.06] text-center"
            >
              <div className="text-[10px] font-bold text-slate-300">{stage}</div>
              <div className="mt-1 text-[8px] text-slate-600 flex items-center justify-center gap-1">
                <CircleSlash className="w-2.5 h-2.5" /> NOT REPORTED
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* Registry */}
        <div className="xl:col-span-6 space-y-3">
          <div className="text-[10px] uppercase text-slate-400 font-bold tracking-wider">
            REGISTERED MODEL VERSIONS
          </div>

          {entries.map((entry) => {
            const isSelected = entry.id === active.id;
            return (
              <div
                key={entry.id}
                onClick={() => setSelectedId(entry.id)}
                className={`p-3.5 rounded border transition-all cursor-pointer ${
                  isSelected
                    ? "bg-cyan-950/30 border-cyan-500/50"
                    : "bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04]"
                }`}
              >
                <div className="flex items-center justify-between gap-2 text-xs">
                  <div className="font-bold text-white flex items-center gap-2 min-w-0">
                    <span className="w-2 h-2 rounded-full bg-cyan-400 shrink-0" />
                    <span className="truncate">{entry.name}</span>
                  </div>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-300 border border-white/[0.10] shrink-0">
                    {entry.status ?? "STATUS UNKNOWN"}
                  </span>
                </div>

                <div className="text-[11px] text-slate-400 mt-1">
                  version <span className="font-mono">{entry.version || "unknown"}</span>
                  {entry.modelType ? ` · ${entry.modelType}` : ""}
                </div>

                <div className="mt-2.5 pt-2 border-t border-white/[0.04] text-[10px]">
                  {entry.claimStatus === "REPORTABLE" ? (
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-2.5 h-2.5" /> claim companions present
                    </span>
                  ) : (
                    <span className="text-amber-300">
                      NOT REPORTABLE &mdash; missing{" "}
                      {entry.missingClaimFields.length} of 14 required companions
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Inspector */}
        <div className="xl:col-span-6 bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-3">
          <EntryInspector entry={active} />

          <div
            className={`p-3 rounded border text-xs flex items-start gap-2 ${
              active.claimStatus === "REPORTABLE"
                ? "bg-emerald-950/20 border-emerald-800/40 text-emerald-300"
                : "bg-amber-950/20 border-amber-800/40 text-amber-200"
            }`}
          >
            <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" />
            {active.claimStatus === "REPORTABLE" ? (
              <span>
                Every claim companion required by the statistical claim gate is
                present for this version.
              </span>
            ) : (
              <span>
                This version&rsquo;s performance figures may not be presented as a
                result. Missing:{" "}
                <span className="font-mono text-[10px]">
                  {active.missingClaimFields.join(", ")}
                </span>
                . The figures above are shown as declared metrics, not as a
                validated claim.
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
