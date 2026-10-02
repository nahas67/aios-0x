import React from 'react';
import { BrainCircuit, FlaskConical, Database } from 'lucide-react';
import { researchApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { adaptResearch } from '../../adapters/research';
import { Unavailable } from '../Unavailable';

/**
 * Research workspace: hypotheses + evidence from GET /api/v1/knowledge,
 * calibration from GET /api/v1/research, annotations from GET /api/v1/memory.
 * Previously this tab rendered the strategies component; it now shows the
 * research record. Absent sources render honest empty states.
 */
export const ResearchWorkspace: React.FC = () => {
  const knowledgeQ = useApi(() => researchApi.knowledge());
  const researchQ = useApi(() => researchApi.research());
  const memoryQ = useApi(() => researchApi.memory());

  if (knowledgeQ.loading || researchQ.loading || memoryQ.loading) {
    return <div className="text-xs text-text-muted font-mono p-8">Loading research from /knowledge + /research + /memory…</div>;
  }
  if (knowledgeQ.error && researchQ.error) {
    return <Unavailable title="Research unavailable" reason={knowledgeQ.error ?? researchQ.error ?? "no research payload"} />;
  }

  const adapted = adaptResearch(
    knowledgeQ.error || !knowledgeQ.data ? { available: false } : knowledgeQ.data,
    researchQ.error || !researchQ.data ? null : researchQ.data,
    memoryQ.error || !memoryQ.data ? null : memoryQ.data,
  );

  const memoryEntries = Object.entries(adapted.memoryScalars);

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BrainCircuit className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              RESEARCH &amp; HYPOTHESIS LEDGER
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent font-bold">
              FRAME 9
            </span>
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            Sources: /api/v1/knowledge • /api/v1/research • /api/v1/memory
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-surface-veil border border-border-subtle px-3 py-1.5 rounded">
            <span className="text-text-muted">HYPOTHESES:</span>{' '}
            <span className="text-text-strong font-bold">
              {adapted.knowledgeAvailable ? (adapted.knowledgeTotal ?? adapted.hypotheses.length) : "—"}
            </span>
          </div>
          <div className="bg-surface-veil border border-border-subtle px-3 py-1.5 rounded">
            <span className="text-text-muted">CALIBRATION:</span>{' '}
            <span className="text-accent font-bold">
              {adapted.calibration ? `${adapted.calibration.totalScored} scored` : "—"}
            </span>
          </div>
        </div>
      </div>

      {/* Calibration summary */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center gap-2 pb-3 border-b border-border-subtle">
          <FlaskConical className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
            PREDICTION CALIBRATION (SERVER REPORT)
          </h3>
        </div>
        {adapted.calibration ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 text-xs">
            <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle">
              <div className="text-[9px] text-text-subtle uppercase">Report</div>
              <div className="text-sm font-bold text-text-strong mt-0.5 font-mono">{adapted.calibration.reportId}</div>
            </div>
            <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle">
              <div className="text-[9px] text-text-subtle uppercase">Brier Score</div>
              <div className="text-sm font-bold text-accent mt-0.5 font-mono">{adapted.calibration.brierScore}</div>
            </div>
            <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle">
              <div className="text-[9px] text-text-subtle uppercase">Directional Accuracy</div>
              <div className="text-sm font-bold text-positive mt-0.5 font-mono">{adapted.calibration.directionalAccuracyPct}%</div>
            </div>
            <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle">
              <div className="text-[9px] text-text-subtle uppercase">Reliable</div>
              <div className="text-sm font-bold text-text-strong mt-0.5">{adapted.calibration.reliable ? "YES" : "NO"}</div>
            </div>
          </div>
        ) : (
          <div className="p-4 text-center text-text-subtle text-xs">
            No calibration report published. {researchQ.error ?? ""}
          </div>
        )}
      </div>

      {/* Hypotheses */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-accent" />
            <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
              HYPOTHESES &amp; EVIDENCE
            </h3>
          </div>
          <span className="text-[10px] text-text-muted">
            {Object.entries(adapted.byStatus).map(([k, v]) => `${k}: ${v}`).join(" • ") || "no status breakdown"}
          </span>
        </div>

        {!adapted.knowledgeAvailable ? (
          <div className="mt-3">
            <Unavailable
              title="Knowledge ledger unavailable"
              reason={knowledgeQ.error ?? "the knowledge store published nothing"}
            />
          </div>
        ) : adapted.hypotheses.length === 0 ? (
          <div className="p-6 text-center text-text-subtle text-xs">
            The knowledge ledger is empty. No hypotheses have been recorded yet.
          </div>
        ) : (
          <div className="space-y-2 mt-3">
            {adapted.hypotheses.map((h) => (
              <div key={h.id} className="p-3 rounded bg-surface-veil border border-border-subtle text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold text-text-strong">{h.statement}</span>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-surface-veil text-text border border-border-strong">
                    {h.status}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-[10px] text-text-muted font-mono-num">
                  <span>ID: <strong className="text-text">{h.id}</strong></span>
                  <span>symbol: <strong className="text-text">{h.symbol ?? "—"}</strong></span>
                  <span>confidence: <strong className="text-accent">{h.confidence ?? "—"}</strong></span>
                  <span>evidence: <strong className="text-text">{h.evidenceTotal}</strong></span>
                  <span className="text-positive">supports {h.supports}</span>
                  <span className="text-destructive">contradicts {h.contradicts}</span>
                  <span>updated: {h.lastUpdated}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Memory annotations */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center gap-2 pb-3 border-b border-border-subtle">
          <Database className="w-4 h-4 text-violet" />
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
            MEMORY ANNOTATIONS
          </h3>
        </div>
        {memoryEntries.length === 0 ? (
          <div className="p-4 text-center text-text-subtle text-xs">
            No scalar memory annotations published. {memoryQ.error ?? ""}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mt-3 text-xs">
            {memoryEntries.map(([k, v]) => (
              <div key={k} className="p-2.5 rounded bg-surface-sunken border border-border-subtle flex items-center justify-between gap-2">
                <span className="text-text-muted text-[10px] truncate" title={k}>{k}</span>
                <span className="text-text-strong font-mono-num text-[11px] truncate" title={v}>{v}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
