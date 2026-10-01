import React from 'react';
import {
  Server,
  Cpu,
  ShieldCheck,
  Wifi,
  HardDrive,
} from 'lucide-react';
import { executiveApi, kernelApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { useLiveExecutive } from '../../hooks/useLiveExecutive';
import { Unavailable } from '../Unavailable';

/**
 * System health derived from GET /api/v1/health + /api/v1/financial/health.
 * No hardcoded service counts, latencies, or memory figures: every number
 * on screen is traceable to one of those two endpoints.
 */
export const SystemHealthWorkspace: React.FC = () => {
  const healthQ = useApi(() => executiveApi.health());
  const kernelQ = useApi(() => kernelApi.health());
  // Starts the SSE stream and exposes the executive snapshot with an honest
  // provenance label. Polling continues underneath while the stream is down, so
  // this panel is never blank merely because the socket is.
  const live = useLiveExecutive();

  if (healthQ.loading || kernelQ.loading) {
    return <div className="text-xs text-slate-400 font-mono p-8">Loading system health from /api/v1/health + /financial/health…</div>;
  }
  if (healthQ.error || !healthQ.data) {
    return <Unavailable title="System health unavailable" reason={healthQ.error ?? "no health payload"} />;
  }
  const health = healthQ.data;
  const kernel = kernelQ.data;

  const components = Object.entries(health.components);
  const wiredCount = components.filter(([, v]) => v).length;

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              SYSTEM HEALTH & WIRED SERVICES
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 13
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Source: /api/v1/health • Audit chain {health.audit_chain_valid ? "valid" : "BROKEN"}
            {health.first_bad_seq != null ? ` (first bad seq ${health.first_bad_seq})` : ""}
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">COMPONENTS WIRED:</span>{' '}
            <span className="text-emerald-400 font-bold">{wiredCount} / {components.length}</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">AUDIT CHAIN:</span>{' '}
            <span className={`font-bold ${health.audit_chain_valid ? 'text-emerald-400' : 'text-rose-400'}`}>
              {health.audit_chain_valid ? "VALID" : "BROKEN"}
            </span>
          </div>
        </div>
      </div>

      {/* Wiring + event counts from the live payload */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-3 shadow-2xl flex items-center gap-3">
          <Cpu className="w-6 h-6 text-cyan-400" />
          <div>
            <div className="text-[10px] text-slate-400">EVENTS LOGGED</div>
            <div className="text-base font-bold text-white font-mono-num">
              {(health.counts.event_log ?? 0).toLocaleString()}
            </div>
          </div>
        </div>

        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-3 shadow-2xl flex items-center gap-3">
          <HardDrive className="w-6 h-6 text-indigo-400" />
          <div>
            <div className="text-[10px] text-slate-400">PREDICTIONS SCORED</div>
            <div className="text-base font-bold text-white font-mono-num">
              {(health.counts.predictions ?? 0).toLocaleString()}
            </div>
          </div>
        </div>

        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-3 shadow-2xl flex items-center gap-3">
          <Wifi className="w-6 h-6 text-emerald-400" />
          <div>
            <div className="text-[10px] text-slate-400">POSTMORTEMS</div>
            <div className="text-base font-bold text-emerald-400 font-mono-num">
              {(health.counts.postmortems ?? 0).toLocaleString()}
            </div>
          </div>
        </div>

        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-3 shadow-2xl flex items-center gap-3">
          <ShieldCheck className="w-6 h-6 text-cyan-400" />
          <div>
            <div className="text-[10px] text-slate-400">FINANCIAL KERNEL</div>
            <div className="text-base font-bold text-cyan-300">
              {kernel == null
                ? "—"
                : kernel.available === true
                  ? (kernel.backend ?? "WIRED")
                  : "NOT WIRED"}
            </div>
          </div>
        </div>
      </div>

      {/* Live stream provenance.
          Reports the feed's own status and, separately, where the executive
          snapshot came from. The two are never merged: a panel labelled LIVE
          while rendering a value a fallback poll fetched 30 seconds ago is the
          exact dishonesty this repository is built to prevent. */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <h3 className="text-xs font-bold uppercase text-white tracking-wider">
            EXECUTIVE STREAM
          </h3>
          <span className="text-[10px] text-slate-400">
            SOURCE: /api/v1/stream + /api/v1/executive
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 my-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-2 rounded">
            <div className="text-[10px] text-slate-400">FEED</div>
            <div
              className={`font-bold ${live.live ? "text-emerald-400" : "text-amber-400"}`}
              data-testid="stream-status"
            >
              {live.status.toUpperCase().replace("_", " ")}
            </div>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-2 rounded">
            <div className="text-[10px] text-slate-400">SNAPSHOT FROM</div>
            <div
              className={`font-bold ${live.source === "stream" ? "text-emerald-400" : "text-slate-300"}`}
              data-testid="stream-source"
            >
              {live.source === "stream"
                ? "STREAM"
                : live.source === "poll"
                  ? "FALLBACK POLL"
                  : "NONE YET"}
            </div>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-2 rounded">
            <div className="text-[10px] text-slate-400">FRAME AGE</div>
            <div className="font-bold text-slate-200 font-mono-num">
              {live.lastFrameAgeMs === null
                ? "NO FRAME"
                : `${(live.lastFrameAgeMs / 1000).toFixed(1)}s`}
            </div>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-2 rounded">
            <div className="text-[10px] text-slate-400">EMERGENCY STATE</div>
            <div className="font-bold text-slate-200">
              {live.executive?.emergency_state ?? "UNKNOWN"}
            </div>
          </div>
        </div>
        {live.status === "auth_required" && (
          <div className="text-[10px] text-amber-400">
            The stream needs credentials. The values above are still being fetched by
            the fallback poll, which is why they are present at all.
          </div>
        )}
        {live.status === "reconnecting" && (
          <div className="text-[10px] text-amber-400">
            Feed reconnecting. Values above come from the fallback poll and may be
            up to one poll interval stale.
          </div>
        )}
      </div>

      {/* Component wiring matrix */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <h3 className="text-xs font-bold uppercase text-white tracking-wider">
            CONTROL-PLANE WIRING (LIVE)
          </h3>
          <span className="text-[10px] text-slate-400">SOURCE: /api/v1/health components</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 my-3">
          {components.map(([name, wired]) => (
            <div
              key={name}
              className="p-2.5 rounded bg-white/[0.02] border border-white/[0.05] flex items-center justify-between text-xs"
            >
              <div className="font-bold text-slate-200 flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${wired ? 'bg-emerald-400' : 'bg-rose-400'}`}></span>
                <span>{name}</span>
              </div>
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${wired ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-rose-950 text-rose-400 border-rose-800'}`}>
                {wired ? "WIRED" : "ABSENT"}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Financial kernel health */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <h3 className="text-xs font-bold uppercase text-white tracking-wider">
            FINANCIAL KERNEL HEALTH
          </h3>
          <span className="text-[10px] text-slate-400">SOURCE: /api/v1/financial/health</span>
        </div>
        <div className="mt-3">
          {kernelQ.error || !kernel ? (
            <Unavailable title="Kernel health unavailable" reason={kernelQ.error ?? "no kernel payload"} />
          ) : kernel.available !== true ? (
            <Unavailable title="Financial kernel not wired" reason={kernel.reason} />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
                <div className="text-[9px] text-slate-500 uppercase">Backend</div>
                <div className="text-sm font-bold text-white mt-0.5">{kernel.backend ?? "—"}</div>
              </div>
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
                <div className="text-[9px] text-slate-500 uppercase">Outbox backlog</div>
                <div className="text-sm font-bold text-cyan-300 mt-0.5">{kernel.outbox_backlog ?? "—"}</div>
              </div>
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
                <div className="text-[9px] text-slate-500 uppercase">Dead letters</div>
                <div className="text-sm font-bold text-amber-300 mt-0.5">{kernel.dead_letters ?? "—"}</div>
              </div>
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
                <div className="text-[9px] text-slate-500 uppercase">Active lockouts</div>
                <div className="text-sm font-bold text-slate-200 mt-0.5">{kernel.active_lockouts ?? "—"}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
