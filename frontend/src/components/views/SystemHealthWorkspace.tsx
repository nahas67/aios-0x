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
    return <div className="text-xs text-text-muted font-mono p-8">Loading system health from /api/v1/health + /financial/health…</div>;
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
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              SYSTEM HEALTH & WIRED SERVICES
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
              FRAME 13
            </span>
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            Source: /api/v1/health • Audit chain {health.audit_chain_valid ? "valid" : "BROKEN"}
            {health.first_bad_seq != null ? ` (first bad seq ${health.first_bad_seq})` : ""}
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-surface-veil border border-border-subtle px-3 py-1.5 rounded">
            <span className="text-text-muted">COMPONENTS WIRED:</span>{' '}
            <span className="text-positive font-bold">{wiredCount} / {components.length}</span>
          </div>
          <div className="bg-surface-veil border border-border-subtle px-3 py-1.5 rounded">
            <span className="text-text-muted">AUDIT CHAIN:</span>{' '}
            <span className={`font-bold ${health.audit_chain_valid ? 'text-positive' : 'text-destructive'}`}>
              {health.audit_chain_valid ? "VALID" : "BROKEN"}
            </span>
          </div>
        </div>
      </div>

      {/* Wiring + event counts from the live payload */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-3 shadow-2xl flex items-center gap-3">
          <Cpu className="w-6 h-6 text-accent" />
          <div>
            <div className="text-[10px] text-text-muted">EVENTS LOGGED</div>
            <div className="text-base font-bold text-text-strong font-mono-num">
              {(health.counts.event_log ?? 0).toLocaleString()}
            </div>
          </div>
        </div>

        <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-3 shadow-2xl flex items-center gap-3">
          <HardDrive className="w-6 h-6 text-violet" />
          <div>
            <div className="text-[10px] text-text-muted">PREDICTIONS SCORED</div>
            <div className="text-base font-bold text-text-strong font-mono-num">
              {(health.counts.predictions ?? 0).toLocaleString()}
            </div>
          </div>
        </div>

        <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-3 shadow-2xl flex items-center gap-3">
          <Wifi className="w-6 h-6 text-positive" />
          <div>
            <div className="text-[10px] text-text-muted">POSTMORTEMS</div>
            <div className="text-base font-bold text-positive font-mono-num">
              {(health.counts.postmortems ?? 0).toLocaleString()}
            </div>
          </div>
        </div>

        <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-3 shadow-2xl flex items-center gap-3">
          <ShieldCheck className="w-6 h-6 text-accent" />
          <div>
            <div className="text-[10px] text-text-muted">FINANCIAL KERNEL</div>
            <div className="text-base font-bold text-accent">
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
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
            EXECUTIVE STREAM
          </h3>
          <span className="text-[10px] text-text-muted">
            SOURCE: /api/v1/stream + /api/v1/executive
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 my-3 text-xs">
          <div className="bg-surface-veil border border-border-subtle px-3 py-2 rounded">
            <div className="text-[10px] text-text-muted">FEED</div>
            <div
              className={`font-bold ${live.live ? "text-positive" : "text-warning"}`}
              data-testid="stream-status"
            >
              {live.status.toUpperCase().replace("_", " ")}
            </div>
          </div>
          <div className="bg-surface-veil border border-border-subtle px-3 py-2 rounded">
            <div className="text-[10px] text-text-muted">SNAPSHOT FROM</div>
            <div
              className={`font-bold ${live.source === "stream" ? "text-positive" : "text-text"}`}
              data-testid="stream-source"
            >
              {live.source === "stream"
                ? "STREAM"
                : live.source === "poll"
                  ? "FALLBACK POLL"
                  : live.source === "stream_stale"
                    ? "STREAM (STALE)"
                    : "NONE YET"}
            </div>
          </div>
          <div className="bg-surface-veil border border-border-subtle px-3 py-2 rounded">
            <div className="text-[10px] text-text-muted">FRAME AGE</div>
            <div className="font-bold text-text-strong font-mono-num">
              {live.lastFrameAt === null
                ? "NO FRAME"
                : `${((Date.now() - live.lastFrameAt) / 1000).toFixed(1)}s`}
            </div>
          </div>
          <div className="bg-surface-veil border border-border-subtle px-3 py-2 rounded">
            <div className="text-[10px] text-text-muted">EMERGENCY STATE</div>
            <div className="font-bold text-text-strong">
              {live.executive?.emergency_state ?? "UNKNOWN"}
            </div>
          </div>
        </div>
        {live.status === "auth_required" && (
          <div className="text-[10px] text-warning">
            The stream needs credentials. The values above are still being fetched by
            the fallback poll, which is why they are present at all.
          </div>
        )}
        {live.status === "reconnecting" && (
          <div className="text-[10px] text-warning">
            Feed reconnecting. {live.source === "stream_stale"
              ? "The value shown is the last one the stream delivered, and no fallback poll has run yet."
              : "Values above come from the fallback poll and may be up to one poll interval stale."}
          </div>
        )}
      </div>

      {/* Component wiring matrix */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
            CONTROL-PLANE WIRING (LIVE)
          </h3>
          <span className="text-[10px] text-text-muted">SOURCE: /api/v1/health components</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 my-3">
          {components.map(([name, wired]) => (
            <div
              key={name}
              className="p-2.5 rounded bg-surface-veil border border-border-subtle flex items-center justify-between text-xs"
            >
              <div className="font-bold text-text-strong flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${wired ? 'bg-positive' : 'bg-destructive'}`}></span>
                <span>{name}</span>
              </div>
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${wired ? 'bg-positive-bg text-positive border-positive' : 'bg-destructive-bg text-destructive border-destructive'}`}>
                {wired ? "WIRED" : "ABSENT"}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Financial kernel health */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
            FINANCIAL KERNEL HEALTH
          </h3>
          <span className="text-[10px] text-text-muted">SOURCE: /api/v1/financial/health</span>
        </div>
        <div className="mt-3">
          {kernelQ.error || !kernel ? (
            <Unavailable title="Kernel health unavailable" reason={kernelQ.error ?? "no kernel payload"} />
          ) : kernel.available !== true ? (
            <Unavailable title="Financial kernel not wired" reason={kernel.reason} />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle">
                <div className="text-[9px] text-text-subtle uppercase">Backend</div>
                <div className="text-sm font-bold text-text-strong mt-0.5">{kernel.backend ?? "—"}</div>
              </div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle">
                <div className="text-[9px] text-text-subtle uppercase">Outbox backlog</div>
                <div className="text-sm font-bold text-accent mt-0.5">{kernel.outbox_backlog ?? "—"}</div>
              </div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle">
                <div className="text-[9px] text-text-subtle uppercase">Dead letters</div>
                <div className="text-sm font-bold text-warning mt-0.5">{kernel.dead_letters ?? "—"}</div>
              </div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle">
                <div className="text-[9px] text-text-subtle uppercase">Active lockouts</div>
                <div className="text-sm font-bold text-text-strong mt-0.5">{kernel.active_lockouts ?? "—"}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
