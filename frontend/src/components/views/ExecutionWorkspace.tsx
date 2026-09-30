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
import { adaptOrders } from '../../adapters/orders';
import { Unavailable } from '../Unavailable';

interface ExecutionWorkspaceProps {
  onSelectOrder?: (order: ExecutionOrder) => void;
  onAddOrder?: (order: ExecutionOrder) => void;
}

/**
 * Execution workspace wired to GET /api/v1/orders.
 * The hardcoded algorithmic slicer jobs are deleted: no slicing engine
 * state is published by the backend, so progress bars it showed were theater.
 * (L2 depth book + venue grid untouched — separate backend gaps.)
 */
export const ExecutionWorkspace: React.FC<ExecutionWorkspaceProps> = ({
  onSelectOrder,
  onAddOrder,
}) => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [selectedAssetDepth, setSelectedAssetDepth] = useState<string>('BTC/USD');
  const [activeTab, setActiveTab] = useState<'tape' | 'depth' | 'analytics'>('tape');
  const [localOrders, setLocalOrders] = useState<ExecutionOrder[]>([]);

  const ordersQ = useApi(() => portfolioApi.orders());

  const handleDispatchNewOrder = (newOrder: ExecutionOrder) => {
    setLocalOrders(prev => [newOrder, ...prev]);
    if (onAddOrder) {
      onAddOrder(newOrder);
    }
  };

  if (ordersQ.loading) {
    return <div className="text-xs text-slate-400 font-mono p-8">Loading orders from /api/v1/orders…</div>;
  }
  if (ordersQ.error || !ordersQ.data) {
    return <Unavailable title="Execution unavailable" reason={ordersQ.error ?? "no orders payload"} />;
  }
  const adapted = adaptOrders(ordersQ.data);
  if ("unavailable" in adapted) {
    return <Unavailable title="Execution unavailable" reason={adapted.unavailable} />;
  }
  const orders = [...localOrders, ...adapted];

  const venues = [
    { name: 'Binance Institutional', volume: '$42.8M', fillRate: '99.98%', latency: '1.2ms', status: 'OPTIMAL' },
    { name: 'CME Group Direct', volume: '$38.2M', fillRate: '100.0%', latency: '2.8ms', status: 'OPTIMAL' },
    { name: 'Hyperliquid Perps', volume: '$28.4M', fillRate: '99.94%', latency: '0.8ms', status: 'LOW_LATENCY' },
    { name: 'Coinbase Prime', volume: '$18.9M', fillRate: '100.0%', latency: '3.4ms', status: 'OPTIMAL' },
    { name: 'Interactive Brokers', volume: '$15.9M', fillRate: '99.99%', latency: '4.1ms', status: 'OPTIMAL' },
  ];

  // Mock Depth Book Data
  const depthData = {
    'BTC/USD': {
      bids: [
        { price: 64195, size: 4.8, total: 4.8, pct: 45 },
        { price: 64190, size: 8.2, total: 13.0, pct: 68 },
        { price: 64185, size: 12.5, total: 25.5, pct: 85 },
        { price: 64180, size: 18.0, total: 43.5, pct: 100 },
      ],
      asks: [
        { price: 64205, size: 5.1, total: 5.1, pct: 48 },
        { price: 64210, size: 9.4, total: 14.5, pct: 72 },
        { price: 64215, size: 14.2, total: 28.7, pct: 90 },
        { price: 64220, size: 16.8, total: 45.5, pct: 100 },
      ]
    },
    'ETH/USD': {
      bids: [
        { price: 3448, size: 42.0, total: 42.0, pct: 50 },
        { price: 3445, size: 85.5, total: 127.5, pct: 75 },
        { price: 3440, size: 140.0, total: 267.5, pct: 100 },
      ],
      asks: [
        { price: 3452, size: 38.5, total: 38.5, pct: 45 },
        { price: 3455, size: 92.0, total: 130.5, pct: 80 },
        { price: 3460, size: 155.0, total: 285.5, pct: 100 },
      ]
    },
    'NVDA': {
      bids: [
        { price: 128.45, size: 12400, total: 12400, pct: 55 },
        { price: 128.40, size: 28000, total: 40400, pct: 82 },
        { price: 128.35, size: 45000, total: 85400, pct: 100 },
      ],
      asks: [
        { price: 128.55, size: 15200, total: 15200, pct: 60 },
        { price: 128.60, size: 31000, total: 46200, pct: 88 },
        { price: 128.65, size: 42000, total: 88200, pct: 100 },
      ]
    }
  };

  const currentDepth = depthData[selectedAssetDepth as keyof typeof depthData] || depthData['BTC/USD'];

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              INSTITUTIONAL EXECUTION WORKSPACE & ORDER ROUTER
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 8 & 16
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            {orders.length} orders • Source: /api/v1/orders
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="px-3 py-1.5 rounded bg-cyan-500 hover:bg-cyan-400 text-black font-bold transition-all shadow-[0_0_12px_rgba(0,240,255,0.4)] flex items-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>DISPATCH NEW ORDER</span>
          </button>
        </div>
      </div>

      {/* Order state summary from the live payload */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase text-white tracking-wider">
              ORDER STATES (BACKEND-REPORTED)
            </h3>
          </div>
          <span className="text-[10px] text-cyan-300 font-bold">
            {orders.length} ORDERS TRACKED
          </span>
        </div>
        {orders.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-xs">
            No orders in the order manager yet. Dispatched orders will appear here.
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-3 text-xs">
            {(['FILLED', 'ROUTING', 'PARTIAL', 'CANCELLED'] as const).map((s) => (
              <div key={s} className="p-2.5 rounded bg-white/[0.02] border border-white/[0.06] text-center">
                <div className="text-[9px] text-slate-500 uppercase">{s}</div>
                <div className="text-base font-mono-num font-bold text-white">
                  {orders.filter((o) => o.orderState === s).length}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sub-view switcher: Tape vs Order Book Liquidity Depth */}
      <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('tape')}
            className={`px-3 py-1 rounded text-xs transition-colors flex items-center gap-1.5 ${
              activeTab === 'tape'
                ? 'bg-cyan-950 text-cyan-300 border border-cyan-700/60 font-bold'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>REAL-TIME EXECUTION TAPE</span>
          </button>
          <button
            onClick={() => setActiveTab('depth')}
            className={`px-3 py-1 rounded text-xs transition-colors flex items-center gap-1.5 ${
              activeTab === 'depth'
                ? 'bg-cyan-950 text-cyan-300 border border-cyan-700/60 font-bold'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <BarChart2 className="w-3.5 h-3.5" />
            <span>MULTI-VENUE LIQUIDITY DEPTH</span>
          </button>
        </div>

        {activeTab === 'depth' && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-400">SELECT ASSET:</span>
            {['BTC/USD', 'ETH/USD', 'NVDA'].map((sym) => (
              <button
                key={sym}
                onClick={() => setSelectedAssetDepth(sym)}
                className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                  selectedAssetDepth === sym
                    ? 'bg-cyan-900 text-cyan-200 font-bold'
                    : 'bg-black/40 text-slate-400 hover:text-slate-200'
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
        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
            <div>
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                CONSOLIDATED ORDER BOOK DEPTH — {selectedAssetDepth}
              </h3>
              <p className="text-[10px] text-slate-400">Aggregated FIX feeds from Binance, CME, Hyperliquid &amp; Coinbase</p>
            </div>
            <div className="text-right text-xs">
              <span className="text-slate-400">MIDPOINT:</span>{' '}
              <span className="text-cyan-300 font-bold font-mono">
                {selectedAssetDepth === 'BTC/USD' ? '$64,200.00' : selectedAssetDepth === 'ETH/USD' ? '$3,450.00' : '$128.50'}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Bids */}
            <div className="space-y-2 p-3 rounded bg-black/40 border border-white/[0.06]">
              <div className="flex justify-between text-[10px] text-slate-400 uppercase font-bold border-b border-white/[0.06] pb-1">
                <span>BID SIZE</span>
                <span>TOTAL ACCUM</span>
                <span>BID PRICE ($)</span>
              </div>
              {currentDepth.bids.map((b, i) => (
                <div key={i} className="relative flex justify-between items-center text-xs py-1 px-1">
                  <div
                    className="absolute right-0 top-0 bottom-0 bg-emerald-950/40 rounded pointer-events-none"
                    style={{ width: `${b.pct}%` }}
                  />
                  <span className="relative text-slate-300 font-mono">{b.size.toLocaleString()}</span>
                  <span className="relative text-slate-500 font-mono">{b.total.toLocaleString()}</span>
                  <span className="relative text-emerald-400 font-bold font-mono">${b.price.toLocaleString()}</span>
                </div>
              ))}
            </div>

            {/* Asks */}
            <div className="space-y-2 p-3 rounded bg-black/40 border border-white/[0.06]">
              <div className="flex justify-between text-[10px] text-slate-400 uppercase font-bold border-b border-white/[0.06] pb-1">
                <span>ASK PRICE ($)</span>
                <span>TOTAL ACCUM</span>
                <span>ASK SIZE</span>
              </div>
              {currentDepth.asks.map((a, i) => (
                <div key={i} className="relative flex justify-between items-center text-xs py-1 px-1">
                  <div
                    className="absolute left-0 top-0 bottom-0 bg-rose-950/40 rounded pointer-events-none"
                    style={{ width: `${a.pct}%` }}
                  />
                  <span className="relative text-rose-400 font-bold font-mono">${a.price.toLocaleString()}</span>
                  <span className="relative text-slate-500 font-mono">{a.total.toLocaleString()}</span>
                  <span className="relative text-slate-300 font-mono">{a.size.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Institutional Execution Venues Grid */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase text-white tracking-wider">
              CONNECTED INSTITUTIONAL VENUES & SMART ORDER ROUTING
            </h3>
          </div>
          <span className="text-[10px] text-emerald-400 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            5/5 VENUES HEALTHY
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 my-3">
          {venues.map((v) => (
            <div key={v.name} className="p-3 rounded bg-white/[0.02] border border-white/[0.06] text-xs">
              <div className="font-bold text-white truncate flex items-center justify-between">
                <span>{v.name}</span>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              </div>
              <div className="mt-2 space-y-1 text-[11px] text-slate-400">
                <div className="flex justify-between">
                  <span>24h Vol:</span>
                  <span className="text-white font-mono-num">{v.volume}</span>
                </div>
                <div className="flex justify-between">
                  <span>Fill Rate:</span>
                  <span className="text-emerald-400 font-mono-num">{v.fillRate}</span>
                </div>
                <div className="flex justify-between">
                  <span>Latency:</span>
                  <span className="text-cyan-300 font-mono-num">{v.latency}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Create Order Modal */}
      <CreateOrderModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onDispatchOrder={handleDispatchNewOrder}
      />
    </div>
  );
};
