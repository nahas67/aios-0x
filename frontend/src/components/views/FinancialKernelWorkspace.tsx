import React, { useState } from 'react';
import { kernelApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { Unavailable } from '../Unavailable';
import { StateView } from '../StateView';
import { classifyList } from '../../lib/stateView';

const KERNEL_POSITIONS_SOURCE = '/api/v1/financial/positions';
const KERNEL_ORDERS_SOURCE = '/api/v1/financial/orders';
const KERNEL_FILLS_SOURCE = '/api/v1/financial/fills';
import { fmtDateTime, fmtNum, fmtPrice, fmtUsd } from '../../lib/format';

type Section =
  | 'ibor' | 'positions' | 'cash' | 'orders' | 'fills'
  | 'invariants' | 'health' | 'outbox' | 'reconciliation';

const SECTIONS: { id: Section; label: string; endpoint: string }[] = [
  { id: 'ibor', label: 'Book of Record', endpoint: '/api/v1/financial/ibor' },
  { id: 'positions', label: 'Positions', endpoint: '/api/v1/financial/positions' },
  { id: 'cash', label: 'Cash & Reservations', endpoint: '/api/v1/financial/cash' },
  { id: 'orders', label: 'Orders', endpoint: '/api/v1/financial/orders' },
  { id: 'fills', label: 'Fills', endpoint: '/api/v1/financial/fills' },
  { id: 'invariants', label: 'Invariants', endpoint: '/api/v1/financial/invariants' },
  { id: 'health', label: 'Health', endpoint: '/api/v1/financial/health' },
  { id: 'outbox', label: 'Outbox', endpoint: '/api/v1/financial/outbox' },
  { id: 'reconciliation', label: 'Reconciliation', endpoint: '/api/v1/financial/reconciliation' },
];

function fmtMinor(v: number | null | undefined): string {
  return v == null ? "—" : fmtUsd(v / 100);
}

function Panel({ title, endpoint, children }: { title: string; endpoint: string; children: React.ReactNode }) {
  return (
    <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
      <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
        <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">{title}</h3>
        <span className="text-[10px] text-text-subtle font-mono">SOURCE: {endpoint}</span>
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

/**
 * Financial Kernel workspace: the durable book of record behind
 * /api/v1/financial/*. Every section handles {available:false, reason}
 * via <Unavailable> — an unwired kernel renders as absence, never as an
 * empty book. Read-only by construction (all GETs).
 */
export const FinancialKernelWorkspace: React.FC = () => {
  const [section, setSection] = useState<Section>('ibor');

  const iborQ = useApi(() => kernelApi.ibor());
  const positionsQ = useApi(() => kernelApi.positions());
  const cashQ = useApi(() => kernelApi.cash());
  const ordersQ = useApi(() => kernelApi.orders());
  const fillsQ = useApi(() => kernelApi.fills());
  const invariantsQ = useApi(() => kernelApi.invariants());
  const healthQ = useApi(() => kernelApi.health());
  const outboxQ = useApi(() => kernelApi.outbox());
  const reconQ = useApi(() => kernelApi.reconciliation());

  const renderSection = () => {
    switch (section) {
      case 'ibor': {
        const q = iborQ;
        if (q.loading) return <div className="text-xs text-text-subtle font-mono">Loading IBOR…</div>;
        if (q.error || !q.data) return <Unavailable title="Book of Record unavailable" reason={q.error ?? "no payload"} />;
        if (q.data.available !== true) return <Unavailable title="Book of Record unavailable" reason={q.data.reason} />;
        const b = q.data;
        return (
          <Panel title={`Book of Record · snapshot ${b.snapshot_id}`} endpoint="/api/v1/financial/ibor">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">NAV</div><div className="text-sm font-bold text-text-strong">{b.nav != null ? fmtUsd(b.nav) : "— (marks incomplete)"}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Gross exposure</div><div className="text-sm font-bold text-text-strong">{b.gross_exposure != null ? fmtUsd(b.gross_exposure) : "—"}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Unrealized P&amp;L</div><div className="text-sm font-bold text-text-strong">{b.unrealized_pnl != null ? fmtUsd(b.unrealized_pnl) : "—"}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Realized P&amp;L</div><div className="text-sm font-bold text-text-strong">{fmtUsd(b.realized_pnl)}</div></div>
            </div>
            <div className="text-[11px] text-text-muted mb-2">as of {fmtDateTime(b.as_of)} • account {b.account_id} • fills applied {b.fills_applied} • marks complete: {String(b.marks_complete)}</div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead><tr className="border-b border-border-subtle text-text-subtle text-[9px] uppercase tracking-wider">
                  <th className="py-2 px-2">Symbol</th><th className="py-2 px-2 text-right">Qty</th><th className="py-2 px-2 text-right">Avg cost</th><th className="py-2 px-2 text-right">Mark</th><th className="py-2 px-2 text-right">Market value</th><th className="py-2 px-2 text-right">Unrealized</th>
                </tr></thead>
                <tbody className="divide-y divide-surface-veil">
                  {b.positions.map((p) => (
                    <tr key={p.symbol}>
                      <td className="py-2 px-2 font-bold text-text-strong">{p.symbol}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text">{fmtNum(p.quantity)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-muted">{fmtPrice(p.avg_cost)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-strong">{fmtPrice(p.mark_price)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-strong">{p.market_value != null ? fmtUsd(p.market_value) : "—"}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-strong">{p.unrealized_pnl != null ? fmtUsd(p.unrealized_pnl) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {b.positions.length === 0 && (
                <StateView state={classifyList(b.positions, KERNEL_POSITIONS_SOURCE)} noun="kernel positions" compact />
              )}
            </div>
          </Panel>
        );
      }
      case 'positions': {
        const q = positionsQ;
        if (q.loading) return <div className="text-xs text-text-subtle font-mono">Loading positions…</div>;
        if (q.error || !q.data) return <Unavailable title="Positions unavailable" reason={q.error ?? "no payload"} />;
        if (q.data.available !== true) return <Unavailable title="Positions unavailable" reason={q.data.reason} />;
        return (
          <Panel title={`Kernel positions (${q.data.positions.length})`} endpoint="/api/v1/financial/positions">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead><tr className="border-b border-border-subtle text-text-subtle text-[9px] uppercase tracking-wider">
                  <th className="py-2 px-2">Account</th><th className="py-2 px-2">Symbol</th><th className="py-2 px-2 text-right">Qty</th><th className="py-2 px-2 text-right">Avg cost</th><th className="py-2 px-2 text-right">Realized P&amp;L</th><th className="py-2 px-2 text-right">Fees</th><th className="py-2 px-2">Updated</th>
                </tr></thead>
                <tbody className="divide-y divide-surface-veil">
                  {q.data.positions.map((p, i) => (
                    <tr key={`${p.account_id}-${p.symbol}-${i}`}>
                      <td className="py-2 px-2 text-text-muted">{p.account_id}</td>
                      <td className="py-2 px-2 font-bold text-text-strong">{p.symbol}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text">{fmtNum(p.quantity)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-muted">{fmtPrice(p.avg_cost)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-strong">{fmtUsd(p.realized_pnl)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-muted">{fmtUsd(p.fees_paid)}</td>
                      <td className="py-2 px-2 text-text-subtle text-[11px]">{fmtDateTime(p.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {q.data.positions.length === 0 && (
                <StateView state={classifyList(q.data.positions, KERNEL_POSITIONS_SOURCE)} noun="kernel positions" compact />
              )}
            </div>
          </Panel>
        );
      }
      case 'cash': {
        const q = cashQ;
        if (q.loading) return <div className="text-xs text-text-subtle font-mono">Loading cash…</div>;
        if (q.error || !q.data) return <Unavailable title="Cash unavailable" reason={q.error ?? "no payload"} />;
        if (q.data.available !== true) return <Unavailable title="Cash unavailable" reason={q.data.reason} />;
        return (
          <Panel title="Cash & reservations (ledger-derived)" endpoint="/api/v1/financial/cash">
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-left text-xs border-collapse">
                <thead><tr className="border-b border-border-subtle text-text-subtle text-[9px] uppercase tracking-wider">
                  <th className="py-2 px-2">Account</th><th className="py-2 px-2">Ccy</th><th className="py-2 px-2 text-right">Settled</th><th className="py-2 px-2 text-right">Reserved</th><th className="py-2 px-2 text-right">Available</th>
                </tr></thead>
                <tbody className="divide-y divide-surface-veil">
                  {q.data.cash.map((c, i) => (
                    <tr key={`${c.account_id}-${c.currency}-${i}`}>
                      <td className="py-2 px-2 text-text-muted">{c.account_id}</td>
                      <td className="py-2 px-2 font-bold text-text-strong">{c.currency}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-strong">{fmtMinor(c.settled_minor)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-warning">{fmtMinor(c.reserved_minor)}</td>
                      <td className="py-2 px-2 text-right font-mono-num font-bold text-positive">{fmtMinor(c.available_minor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {q.data.cash.length === 0 && <div className="p-4 text-center text-text-subtle text-xs">No cash postings.</div>}
            </div>
            <h4 className="text-[10px] font-bold uppercase text-text-muted mb-2">Reservations ({q.data.reservations.length})</h4>
            <div className="space-y-1.5 text-xs">
              {q.data.reservations.map((r) => (
                <div key={r.reservation_id} className="flex items-center justify-between p-2 rounded bg-surface-veil border border-border-subtle">
                  <span className="text-text-strong">{r.reason} <span className="text-text-subtle">• {r.account_id}</span></span>
                  <span className="font-mono-num text-text">{fmtMinor(r.amount_minor)} {r.active ? "" : "(released)"}</span>
                </div>
              ))}
              {q.data.reservations.length === 0 && <div className="text-text-subtle text-xs">No reservations.</div>}
            </div>
          </Panel>
        );
      }
      case 'orders': {
        const q = ordersQ;
        if (q.loading) return <div className="text-xs text-text-subtle font-mono">Loading orders…</div>;
        if (q.error || !q.data) return <Unavailable title="Orders unavailable" reason={q.error ?? "no payload"} />;
        if (q.data.available !== true) return <Unavailable title="Orders unavailable" reason={q.data.reason} />;
        return (
          <Panel title={`Kernel orders (${q.data.orders.length})`} endpoint="/api/v1/financial/orders">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead><tr className="border-b border-border-subtle text-text-subtle text-[9px] uppercase tracking-wider">
                  <th className="py-2 px-2">Internal ID</th><th className="py-2 px-2">Client ID</th><th className="py-2 px-2">Symbol</th><th className="py-2 px-2">Side</th><th className="py-2 px-2 text-right">Qty</th><th className="py-2 px-2 text-right">Filled</th><th className="py-2 px-2">Status</th><th className="py-2 px-2">Created</th>
                </tr></thead>
                <tbody className="divide-y divide-surface-veil">
                  {q.data.orders.map((o) => (
                    <tr key={o.internal_order_id}>
                      <td className="py-2 px-2 text-accent font-mono text-[11px]">{o.internal_order_id}</td>
                      <td className="py-2 px-2 text-text-muted font-mono text-[11px]">{o.client_order_id}</td>
                      <td className="py-2 px-2 font-bold text-text-strong">{o.symbol}</td>
                      <td className="py-2 px-2 text-text">{o.side}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text">{fmtNum(o.quantity)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text">{fmtNum(o.filled_quantity)}</td>
                      <td className="py-2 px-2 text-[11px] text-text-strong">{o.status}</td>
                      <td className="py-2 px-2 text-text-subtle text-[11px]">{fmtDateTime(o.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {q.data.orders.length === 0 && (
                <StateView state={classifyList(q.data.orders, KERNEL_ORDERS_SOURCE)} noun="kernel orders" compact />
              )}
            </div>
          </Panel>
        );
      }
      case 'fills': {
        const q = fillsQ;
        if (q.loading) return <div className="text-xs text-text-subtle font-mono">Loading fills…</div>;
        if (q.error || !q.data) return <Unavailable title="Fills unavailable" reason={q.error ?? "no payload"} />;
        if (q.data.available !== true) return <Unavailable title="Fills unavailable" reason={q.data.reason} />;
        return (
          <Panel title={`Kernel fills (${q.data.fills.length})`} endpoint="/api/v1/financial/fills">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead><tr className="border-b border-border-subtle text-text-subtle text-[9px] uppercase tracking-wider">
                  <th className="py-2 px-2">Fill ID</th><th className="py-2 px-2">Symbol</th><th className="py-2 px-2">Side</th><th className="py-2 px-2 text-right">Qty</th><th className="py-2 px-2 text-right">Price</th><th className="py-2 px-2 text-right">Fee</th><th className="py-2 px-2">Executed</th>
                </tr></thead>
                <tbody className="divide-y divide-surface-veil">
                  {q.data.fills.map((f) => (
                    <tr key={f.fill_id}>
                      <td className="py-2 px-2 text-accent font-mono text-[11px]">{f.fill_id}</td>
                      <td className="py-2 px-2 font-bold text-text-strong">{f.symbol}</td>
                      <td className="py-2 px-2 text-text">{f.side}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text">{fmtNum(f.quantity)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-strong">{fmtPrice(f.price)}</td>
                      <td className="py-2 px-2 text-right font-mono-num text-text-muted">{fmtUsd(f.fee)}</td>
                      <td className="py-2 px-2 text-text-subtle text-[11px]">{fmtDateTime(f.executed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {q.data.fills.length === 0 && (
                <StateView state={classifyList(q.data.fills, KERNEL_FILLS_SOURCE)} noun="fills" compact />
              )}
            </div>
          </Panel>
        );
      }
      case 'invariants': {
        const q = invariantsQ;
        if (q.loading) return <div className="text-xs text-text-subtle font-mono">Running invariants…</div>;
        if (q.error || !q.data) return <Unavailable title="Invariants unavailable" reason={q.error ?? "no payload"} />;
        if (q.data.available !== true) return <Unavailable title="Invariants unavailable" reason={q.data.reason} />;
        return (
          <Panel title={`Invariant suite — ${q.data.ok ? "ALL PASSING" : "FAILURES PRESENT"} (${q.data.checked} checked)`} endpoint="/api/v1/financial/invariants">
            {q.data.failures.length === 0 ? (
              <div className="p-4 text-center text-positive text-xs">All {q.data.checked} invariants hold.</div>
            ) : (
              <div className="space-y-1.5 text-xs">
                {q.data.failures.map((f, i) => (
                  <div key={i} className="p-2 rounded bg-destructive-bg border border-destructive">
                    <div className="font-bold text-destructive">{f.name}</div>
                    <div className="text-text text-[11px]">{f.detail}</div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        );
      }
      case 'health': {
        const q = healthQ;
        if (q.loading) return <div className="text-xs text-text-subtle font-mono">Loading kernel health…</div>;
        if (q.error || !q.data) return <Unavailable title="Kernel health unavailable" reason={q.error ?? "no payload"} />;
        if (q.data.available !== true) return <Unavailable title="Kernel health unavailable" reason={q.data.reason} />;
        const h = q.data;
        return (
          <Panel title="Kernel health" endpoint="/api/v1/financial/health">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Backend</div><div className="text-sm font-bold text-text-strong">{h.backend ?? "—"}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Reachable</div><div className="text-sm font-bold text-text-strong">{h.reachable == null ? "—" : String(h.reachable)}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Outbox backlog</div><div className="text-sm font-bold text-accent">{h.outbox_backlog ?? "—"}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Dead letters</div><div className="text-sm font-bold text-warning">{h.dead_letters ?? "—"}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Open findings</div><div className="text-sm font-bold text-text-strong">{h.open_findings ?? "—"}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Active lockouts</div><div className="text-sm font-bold text-text-strong">{h.active_lockouts ?? "—"}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Schema</div><div className="text-sm font-bold text-text-strong">{h.schema?.dialect ?? "—"} {h.schema?.current != null ? `@${h.schema.current}` : ""}</div></div>
              <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Schema up to date</div><div className="text-sm font-bold text-text-strong">{h.schema?.up_to_date == null ? "—" : String(h.schema.up_to_date)}</div></div>
            </div>
            {(h.safety?.lockouts ?? []).length > 0 && (
              <div className="mt-3 space-y-1.5 text-xs">
                <h4 className="text-[10px] font-bold uppercase text-destructive">Active lockouts</h4>
                {(h.safety?.lockouts ?? []).map((l) => (
                  <div key={l.lockout_id} className="p-2 rounded bg-destructive-bg border border-destructive">
                    <span className="font-bold text-destructive">{l.scope} / {l.subject}</span>
                    <span className="text-text"> — {l.reason}</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        );
      }
      case 'outbox': {
        const q = outboxQ;
        if (q.loading) return <div className="text-xs text-text-subtle font-mono">Loading outbox…</div>;
        if (q.error || !q.data) return <Unavailable title="Outbox unavailable" reason={q.error ?? "no payload"} />;
        if (q.data.available !== true) return <Unavailable title="Outbox unavailable" reason={q.data.reason} />;
        return (
          <Panel title={`Outbox — backlog ${q.data.backlog}, dead letters ${q.data.dead_letter_count}`} endpoint="/api/v1/financial/outbox">
            {q.data.event_backbone && (
              <div className="text-[11px] text-text-muted mb-3 font-mono">
                backbone wired: {String(q.data.event_backbone.wired)} • consumer lag: {q.data.event_backbone.consumer_lag ?? "unknown"}
                {q.data.event_backbone.reason ? ` • ${q.data.event_backbone.reason}` : ""}
              </div>
            )}
            {q.data.dead_letters.length > 0 && (
              <div className="mb-3 space-y-1.5 text-xs">
                <h4 className="text-[10px] font-bold uppercase text-destructive">Dead letters</h4>
                {q.data.dead_letters.map((d) => (
                  <div key={d.event_id} className="p-2 rounded bg-destructive-bg border border-destructive">
                    <span className="font-bold text-destructive">{d.event_type}</span>
                    <span className="text-text-muted"> • {d.attempts} attempts • {d.last_error ?? "no error recorded"}</span>
                  </div>
                ))}
              </div>
            )}
            <h4 className="text-[10px] font-bold uppercase text-text-muted mb-2">Pending ({q.data.pending.length})</h4>
            <div className="space-y-1.5 text-xs">
              {q.data.pending.map((p) => (
                <div key={p.event_id} className="flex items-center justify-between p-2 rounded bg-surface-veil border border-border-subtle">
                  <span className="text-text-strong">{p.event_type} <span className="text-text-subtle">• {p.status} • {p.attempts} attempts</span></span>
                  <span className="text-text-subtle text-[11px]">{p.claimed_by ?? "unclaimed"}</span>
                </div>
              ))}
              {q.data.pending.length === 0 && <div className="text-text-subtle text-xs">Outbox empty.</div>}
            </div>
          </Panel>
        );
      }
      case 'reconciliation': {
        const q = reconQ;
        if (q.loading) return <div className="text-xs text-text-subtle font-mono">Loading reconciliation…</div>;
        if (q.error || !q.data) return <Unavailable title="Reconciliation unavailable" reason={q.error ?? "no payload"} />;
        if (q.data.available !== true) return <Unavailable title="Reconciliation unavailable" reason={q.data.reason} />;
        const last = q.data.last_run;
        return (
          <Panel title="Reconciliation — broker truth vs internal truth" endpoint="/api/v1/financial/reconciliation">
            {last ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
                <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Last run</div><div className="text-[11px] font-bold text-text-strong">{last.run_id}</div><div className="text-[10px] text-text-subtle">{last.mode} • {fmtDateTime(last.started_at)}</div></div>
                <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Matched</div><div className="text-sm font-bold text-positive">{last.matched_executions}</div></div>
                <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Broker-only / internal-only</div><div className="text-sm font-bold text-text-strong">{last.broker_only_executions} / {last.internal_only_executions}</div></div>
                <div className="p-2.5 rounded bg-surface-sunken border border-border-subtle"><div className="text-[9px] text-text-subtle uppercase">Verdict</div><div className={`text-sm font-bold ${last.ok ? 'text-positive' : 'text-destructive'}`}>{last.ok ? "OK" : "FINDINGS OPEN"}</div></div>
              </div>
            ) : (
              <div className="p-4 text-center text-text-subtle text-xs mb-3">No reconciliation run has completed yet.</div>
            )}
            <h4 className="text-[10px] font-bold uppercase text-text-muted mb-2">Open findings ({q.data.open_findings.length}) — both sides shown</h4>
            <div className="space-y-1.5 text-xs">
              {q.data.open_findings.map((f) => (
                <div key={f.finding_id} className="p-2 rounded bg-surface-veil border border-border-subtle">
                  <div className="font-bold text-text-strong">{f.kind} • {f.severity} • {f.subject}</div>
                  <div className="text-text-muted text-[11px]">{f.detail}</div>
                  <div className="text-[11px] font-mono mt-1">
                    <span className="text-accent">internal: {f.internal_value ?? "—"}</span>
                    <span className="text-text-subtle"> vs </span>
                    <span className="text-warning">broker: {f.broker_value ?? "—"}</span>
                  </div>
                </div>
              ))}
              {q.data.open_findings.length === 0 && <div className="text-text-subtle text-xs">No open findings.</div>}
            </div>
          </Panel>
        );
      }
    }
  };

  return (
    <div className="space-y-4 pb-12 font-mono">
      <div>
        <h1 className="text-lg font-bold text-text-strong">Financial Kernel</h1>
        <p className="text-xs text-text-muted">Durable book of record — read-only. Every section names its source endpoint.</p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setSection(s.id)}
            title={s.endpoint}
            className={`px-2.5 py-1 rounded text-[11px] transition-colors ${
              section === s.id
                ? 'bg-info-bg text-accent border border-accent font-bold'
                : 'bg-surface-veil text-text-muted border border-border-subtle hover:text-text-strong'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
      {renderSection()}
    </div>
  );
};
