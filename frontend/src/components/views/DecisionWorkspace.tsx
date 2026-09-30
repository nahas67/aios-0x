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
    return <div className="text-xs text-slate-400 font-mono p-8">Loading executions from /api/v1/executions…</div>;
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
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Network className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              INVESTMENT DECISION & PROVENANCE WORKSPACE
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 5 & 6
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            {executions.length} closed executions • Full lineage loads per execution from /api/v1/decisions/:id
          </div>
        </div>
      </div>

      {/* Execution selector */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <h3 className="text-xs font-bold uppercase text-white tracking-wider pb-3 border-b border-white/[0.06]">
          CLOSED EXECUTIONS — SELECT FOR FULL LINEAGE
        </h3>
        {executions.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-xs">
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
                    ? 'bg-cyan-950/30 border-cyan-500/50'
                    : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04]'
                }`}
              >
                <span className="font-bold text-white">{e.execution_id}</span>
                <span className="text-slate-400"> • {e.symbol ?? "—"} • {e.action ?? "—"}</span>
                <span className={`ml-2 font-mono-num font-bold ${(e.realized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {e.realized_pnl >= 0 ? '+' : ''}${e.realized_pnl.toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Primary Provenance Lineage Explorer */}
      {activeId && drilldownQ.loading && (
        <div className="text-xs text-slate-400 font-mono p-4">Loading lineage for {activeId}…</div>
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
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Scale className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase text-white tracking-wider">
              PENDING GATED PROPOSALS REQUIRING SUPERVISION
            </h3>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold">
              NO LIVE PROPOSAL FEED
            </span>
          </div>
          <span className="text-[10px] text-slate-400">AUTONOMY: SUPERVISED</span>
        </div>

        {decisionActionStatus ? (
          <div className="p-4 my-3 rounded bg-emerald-950/40 border border-emerald-700/60 text-emerald-300 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>{decisionActionStatus}</span>
            </div>
          </div>
        ) : (
          <div className="my-3 p-6 text-center text-slate-500 text-xs rounded bg-black/20 border border-dashed border-white/[0.08]">
            No pending proposals are published by the backend yet. The approval queue (/api/v1/approvals)
            will appear here once the settings/control plane ships.
          </div>
        )}
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-white/[0.05]">
          <button
            onClick={() => handleAction('No proposal to ratify — the queue is empty.')}
            className="px-4 py-1.5 rounded bg-white/[0.04] hover:bg-white/[0.08] text-xs text-slate-400 hover:text-white transition-colors flex items-center gap-1.5"
          >
            <Zap className="w-3.5 h-3.5" />
            <span>REFRESH QUEUE</span>
          </button>
        </div>
      </div>
    </div>
  );
};
