import React, { useState } from 'react';
import { ExecutionOrder } from '../../types';
import {
  Zap,
  Activity,
  Layers,
  Clock,
  Plus,
  BarChart2,
} from 'lucide-react';
import { LiveExecutionTape } from '../LiveExecutionTape';
import { CreateOrderModal } from '../CreateOrderModal';
import { portfolioApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { useStreamRefresh } from '../../hooks/useStreamRefresh';
import { adaptOrders } from '../../adapters/orders';
import { Unavailable } from '../Unavailable';
import { StateView } from '../StateView';
import { classifyList } from '../../lib/stateView';

/** Named so the empty state can say who looked. */
const EXECUTION_ORDERS_SOURCE = '/api/v1/orders';

interface ExecutionWorkspaceProps {
  onSelectOrder?: (order: ExecutionOrder) => void;
  onNotice?: (msg: string) => void;
}

/**
 * Execution workspace wired to GET /api/v1/orders.
 * The hardcoded algorithmic slicer jobs are deleted: no slicing engine
 * state is published by the backend, so progress bars it showed were theater.
 * Order submission is not wired either (orders are read-only over HTTP), so
 * the create modal stages parameters and reports honestly instead of
 * fabricating fills.
 * Venue routing grid and L2 depth book are honest empty states: the backend
 * publishes no venue telemetry or depth feed (/orders rows carry venue "—"
 * by contract in adapters/orders.ts), so invented latencies and book levels
 * would be theater. They render as "not published" panels until a real feed
 * exists.
 */
export const ExecutionWorkspace: React.FC<ExecutionWorkspaceProps> = ({
  onSelectOrder,
  onNotice,
}) => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [selectedAssetDepth, setSelectedAssetDepth] = useState<string>('BTC/USD');
  const [activeTab, setActiveTab] = useState<'tape' | 'depth' | 'analytics'>('tape');

  // Orders are the live edge of the book: a working order that has since filled or been
  // cancelled must not keep rendering as working. Stream-driven, coalesced.
  const tick = useStreamRefresh();
  const ordersQ = useApi(() => portfolioApi.orders(), [tick]);

  const handleStagedNotice = (msg: string) => {
    if (onNotice) onNotice(msg);
  };

  if (ordersQ.loading) {
    return <div className="text-xs text-text-muted font-mono p-8">Loading orders from /api/v1/orders…</div>;
  }
  if (ordersQ.error || !ordersQ.data) {
    return <Unavailable title="Execution unavailable" reason={ordersQ.error ?? "no orders payload"} />;
  }
  const adapted = adaptOrders(ordersQ.data);
  if ("unavailable" in adapted) {
    return <Unavailable title="Execution unavailable" reason={adapted.unavailable} />;
  }
  const orders = adapted;

  // No venue telemetry is published by the backend (orders carry venue "—"
  // by contract), so there is nothing honest to tabulate here. Derived
  // venue names from orders would all be "—"; show the empty state instead.
  const venueNames: string[] = Array.from(
    new Set(
      orders
        .map((o) => (o.venue ?? "").trim())
        .filter((v) => v.length > 0 && v !== "—"),
    ),
  );

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              INSTITUTIONAL EXECUTION WORKSPACE & ORDER ROUTER
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
              FRAME 8 & 16
            </span>
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            {orders.length} orders • Source: /api/v1/orders
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="px-3 py-1.5 rounded bg-accent hover:bg-accent text-text-strong font-bold transition-all shadow-[0_0_12px_rgba(0,240,255,0.4)] flex items-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>DISPATCH NEW ORDER</span>
          </button>
        </div>
      </div>

      {/* Order state summary from the live payload */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-accent" />
            <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
              ORDER STATES (BACKEND-REPORTED)
            </h3>
          </div>
          <span className="text-[10px] text-accent font-bold">
            {orders.length} ORDERS TRACKED
          </span>
        </div>
        {orders.length === 0 ? (
          <StateView state={classifyList(orders, EXECUTION_ORDERS_SOURCE)} noun="orders" />
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-3 text-xs">
            {(['FILLED', 'ROUTING', 'PARTIAL', 'CANCELLED'] as const).map((s) => (
              <div key={s} className="p-2.5 rounded bg-surface-veil border border-border-subtle text-center">
                <div className="text-[9px] text-text-subtle uppercase">{s}</div>
                <div className="text-base font-mono-num font-bold text-text-strong">
                  {orders.filter((o) => o.orderState === s).length}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sub-view switcher: Tape vs Order Book Liquidity Depth */}
      <div className="flex items-center justify-between border-b border-border-subtle pb-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('tape')}
            className={`px-3 py-1 rounded text-xs transition-colors flex items-center gap-1.5 ${
              activeTab === 'tape'
                ? 'bg-info-bg text-accent border border-accent font-bold'
                : 'text-text-muted hover:text-text-strong'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>REAL-TIME EXECUTION TAPE</span>
          </button>
          <button
            onClick={() => setActiveTab('depth')}
            className={`px-3 py-1 rounded text-xs transition-colors flex items-center gap-1.5 ${
              activeTab === 'depth'
                ? 'bg-info-bg text-accent border border-accent font-bold'
                : 'text-text-muted hover:text-text-strong'
            }`}
          >
            <BarChart2 className="w-3.5 h-3.5" />
            <span>MULTI-VENUE LIQUIDITY DEPTH</span>
          </button>
        </div>

        {activeTab === 'depth' && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-text-muted">SELECT ASSET:</span>
            {['BTC/USD', 'ETH/USD', 'NVDA'].map((sym) => (
              <button
                key={sym}
                onClick={() => setSelectedAssetDepth(sym)}
                className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                  selectedAssetDepth === sym
                    ? 'bg-info-bg text-accent font-bold'
                    : 'bg-surface-sunken text-text-muted hover:text-text-strong'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Main Tab Content */}
      {activeTab === 'tape' ? (
        <LiveExecutionTape
          orders={orders}
          onSelectOrder={onSelectOrder}
        />
      ) : (
        <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-border-subtle">
            <div>
              <h3 className="text-xs font-bold text-text-strong uppercase tracking-wider">
                CONSOLIDATED ORDER BOOK DEPTH — {selectedAssetDepth}
              </h3>
              <p className="text-[10px] text-text-muted">No L2 depth feed is published by the backend</p>
            </div>
          </div>
          <Unavailable
            title="Depth unavailable"
            reason="no market-depth feed is published by the backend for this asset — depth is unknown, not zero"
          />
        </div>
      )}

      {/* Institutional Execution Venues Grid */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-accent" />
            <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
              CONNECTED INSTITUTIONAL VENUES & SMART ORDER ROUTING
            </h3>
          </div>
          <span className="text-[10px] text-text-muted flex items-center gap-1">
            VENUE TELEMETRY NOT PUBLISHED
          </span>
        </div>

        {venueNames.length === 0 ? (
          <div className="my-3">
            <Unavailable
              title="No venue routing state"
              reason="the backend publishes no venue telemetry (latency / fill-rate / volume) — venues are unknown, not healthy"
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 my-3">
            {venueNames.map((name) => (
              <div key={name} className="p-3 rounded bg-surface-veil border border-border-subtle text-xs">
                <div className="font-bold text-text-strong truncate flex items-center justify-between">
                  <span>{name}</span>
                </div>
                <div className="mt-2 text-[11px] text-text-muted">
                  Derived from /api/v1/orders rows. No latency / fill-rate telemetry published.
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Order Modal */}
      <CreateOrderModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onNotice={handleStagedNotice}
      />
    </div>
  );
};
