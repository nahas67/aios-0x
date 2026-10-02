import React, { useState } from 'react';
import {
  Network,
  CheckCircle2,
  Zap,
  Scale,
} from 'lucide-react';
import { DecisionProvenanceExplorer } from '../DecisionProvenanceExplorer';
import { portfolioApi, researchApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { adaptDecisionDrilldown } from '../../adapters/executions';
import { Unavailable } from '../Unavailable';

interface DecisionWorkspaceProps {
  onSelectTrace: (traceId: string) => void;
  onDispatchRatifiedOrder?: (orderDesc: string) => void;
}

/**
 * Provenance workspace wired to GET /api/v1/executions + /api/v1/decisions/{id}.
 * The 4 hardcoded debate scenarios and the 900ms replay timer are deleted:
 * debate replay needs the A1 debates endpoint, which does not exist yet.
 */
export const DecisionWorkspace: React.FC<DecisionWorkspaceProps> = ({
  onSelectTrace,
  onDispatchRatifiedOrder,
}) => {
  const executionsQ = useApi(() => portfolioApi.executions());
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const [decisionActionStatus, setDecisionActionStatus] = useState<string | null>(null);

  const fallbackId = executionsQ.data?.executions[0]?.execution_id ?? null;
  const activeId = selectedExecutionId ?? fallbackId;
  const drilldownQ = useApi(
    () => researchApi.decisions(activeId ?? ""),
    [activeId],
  );

  const handleAction = (status: string) => {
    setDecisionActionStatus(status);
    if (onDispatchRatifiedOrder) {
      onDispatchRatifiedOrder(status);
    }
    setTimeout(() => setDecisionActionStatus(null), 4000);
  };

  if (executionsQ.loading) {
    return <div className="text-xs text-text-muted font-mono p-8">Loading executions from /api/v1/executions…</div>;
  }
  if (executionsQ.error || !executionsQ.data) {
    return <Unavailable title="Provenance unavailable" reason={executionsQ.error ?? "no executions payload"} />;
  }

  const executions = executionsQ.data.executions;

  const adaptedTrace =
    activeId && drilldownQ.data
      ? adaptDecisionDrilldown(drilldownQ.data, executions.find((e) => e.execution_id === activeId))
      : null;
  const drilldownUnavailable =
    adaptedTrace && "unavailable" in adaptedTrace ? adaptedTrace.unavailable : null;

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Network className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              INVESTMENT DECISION & PROVENANCE WORKSPACE
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
              FRAME 5 & 6
            </span>
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            {executions.length} closed executions • Full lineage loads per execution from /api/v1/decisions/:id
          </div>
        </div>
      </div>

      {/* Execution selector */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider pb-3 border-b border-border-subtle">
          CLOSED EXECUTIONS — SELECT FOR FULL LINEAGE
        </h3>
        {executions.length === 0 ? (
          <div className="p-6 text-center text-text-subtle text-xs">
            No closed executions yet. Provenance appears here once trades close.
          </div>
        ) : (
          <div className="mt-2 space-y-1.5 max-h-56 overflow-y-auto">
            {executions.map((e) => (
              <button
                key={e.execution_id}
                onClick={() => setSelectedExecutionId(e.execution_id)}
                className={`w-full text-left p-2.5 rounded border transition-all text-xs ${
                  activeId === e.execution_id
                    ? 'bg-info-bg border-accent'
                    : 'bg-surface-veil border-border-subtle hover:bg-surface-veil'
                }`}
              >
                <span className="font-bold text-text-strong">{e.execution_id}</span>
                <span className="text-text-muted"> • {e.symbol ?? "—"} • {e.action ?? "—"}</span>
                <span className={`ml-2 font-mono-num font-bold ${(e.realized_pnl ?? 0) >= 0 ? 'text-positive' : 'text-destructive'}`}>
                  {e.realized_pnl >= 0 ? '+' : ''}${e.realized_pnl.toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Primary Provenance Lineage Explorer */}
      {activeId && drilldownQ.loading && (
        <div className="text-xs text-text-muted font-mono p-4">Loading lineage for {activeId}…</div>
      )}
      {activeId && drilldownQ.error && (
        <Unavailable title="Lineage unavailable" reason={drilldownQ.error} />
      )}
      {drilldownUnavailable && (
        <Unavailable title="Lineage unavailable" reason={drilldownUnavailable} />
      )}
      {adaptedTrace && !("unavailable" in adaptedTrace) && (
        <DecisionProvenanceExplorer
          traces={[adaptedTrace]}
          selectedTraceId={adaptedTrace.executionId}
          onSelectTrace={(id) => {
            onSelectTrace(id);
          }}
        />
      )}

      {/* Pending Gated Decision Queue */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <div className="flex items-center gap-2">
            <Scale className="w-4 h-4 text-accent" />
            <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
              PENDING GATED PROPOSALS REQUIRING SUPERVISION
            </h3>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-warning-bg text-warning border border-warning font-bold">
              NO LIVE PROPOSAL FEED
            </span>
          </div>
          <span className="text-[10px] text-text-muted">AUTONOMY: SUPERVISED</span>
        </div>

        {decisionActionStatus ? (
          <div className="p-4 my-3 rounded bg-positive-bg border border-positive text-positive text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-positive" />
              <span>{decisionActionStatus}</span>
            </div>
          </div>
        ) : (
          <div className="my-3 p-6 text-center text-text-subtle text-xs rounded bg-surface-sunken border border-dashed border-border-strong">
            No pending proposals are published by the backend yet. The approval queue (/api/v1/approvals)
            will appear here once the settings/control plane ships.
          </div>
        )}
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-border-subtle">
          <button
            onClick={() => handleAction('No proposal to ratify — the queue is empty.')}
            className="px-4 py-1.5 rounded bg-surface-veil hover:bg-surface-raised text-xs text-text-muted hover:text-text-strong transition-colors flex items-center gap-1.5"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>REFRESH QUEUE</span>
          </button>
        </div>
      </div>
    </div>
  );
};
