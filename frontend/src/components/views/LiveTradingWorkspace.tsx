import React, { useState, useMemo } from 'react';
import {
  Search,
  Layers,
  Zap,
  Clock,
  Filter,
  Settings as SettingsIcon,
} from 'lucide-react';
import { SystemSettings, Position } from '../../types';
import { TradingViewAdvancedChart } from '../trading/TradingViewAdvancedChart';
import { OrderBookDOM } from '../trading/OrderBookDOM';
import { TradeTapeTimeSales } from '../trading/TradeTapeTimeSales';
import { OrderExecutionTicket } from '../trading/OrderExecutionTicket';
import { marketApi, portfolioApi, intelligenceApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { useStreamRefresh } from '../../hooks/useStreamRefresh';
import { adaptPositions } from '../../adapters/positions';
import { adaptOrders } from '../../adapters/orders';
import { Unavailable } from '../Unavailable';
import type { Opportunity } from '../../api/types';

interface LiveTradingWorkspaceProps {
  settings: SystemSettings;
  onOpenSettings?: () => void;
  onTriggerToast?: (msg: string) => void;
  onInspectPosition?: (pos: Position) => void;
}

/**
 * Trading workspace. Symbols come from GET /api/v1/market/instruments (no
 * hardcoded list, no prices — the feed publishes none). Candles, positions,
 * orders, and opportunities each come from their own endpoint; the L2 book
 * and tape render honest empty states (no L2/tape source exists).
 */
export const LiveTradingWorkspace: React.FC<LiveTradingWorkspaceProps> = ({
  settings,
  onOpenSettings,
  onTriggerToast,
  onInspectPosition,
}) => {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [activeCategoryFilter, setActiveCategoryFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeBottomTab, setActiveBottomTab] = useState<'POSITIONS' | 'WORKING_ORDERS' | 'EXECUTION_TAPE' | 'AGENT_SIGNALS'>('POSITIONS');
  const [mark, setMark] = useState<number>(0);

  // Positions and orders are the live edge of the book — this is the workspace where a
  // stale working order is most likely to be acted on. Stream-driven and coalesced.
  // Instruments and opportunities are left alone: the former is a slow-moving reference
  // list, and refetching the latter on every tick would be the most expensive call here.
  const tick = useStreamRefresh();
  const instrumentsQ = useApi(() => marketApi.instruments());
  const positionsQ = useApi(() => portfolioApi.positions(), [tick]);
  const ordersQ = useApi(() => portfolioApi.orders(), [tick]);
  const oppsQ = useApi(() => intelligenceApi.opportunities());

  const instruments = useMemo(() => {
    const list = instrumentsQ.data?.instruments ?? [];
    return [...list].sort((a, b) => a.symbol.localeCompare(b.symbol));
  }, [instrumentsQ.data]);

  const categories = useMemo(() => {
    const cats = new Set(instruments.map(i => i.category || 'UNKNOWN'));
    return ['ALL', ...[...cats].sort()];
  }, [instruments]);

  const activeSymbol = selectedSymbol ?? instruments[0]?.symbol ?? null;

  // Filtered Instruments for the Watchlist Bar
  const filteredInstruments = useMemo(() => {
    return instruments.filter(inst => {
      const matchCat = activeCategoryFilter === 'ALL' || (inst.category || 'UNKNOWN') === activeCategoryFilter;
      const q = searchQuery.toLowerCase();
      const matchSearch = q === '' ||
        inst.symbol.toLowerCase().includes(q) ||
        (inst.name || '').toLowerCase().includes(q);
      return matchCat && matchSearch;
    });
  }, [instruments, activeCategoryFilter, searchQuery]);

  const positions = useMemo(() => {
    if (!positionsQ.data) return null;
    const adapted = adaptPositions(positionsQ.data);
    return "unavailable" in adapted ? adapted : adapted;
  }, [positionsQ.data]);

  const orders = useMemo(() => {
    if (!ordersQ.data) return null;
    const adapted = adaptOrders(ordersQ.data);
    return "unavailable" in adapted ? adapted : adapted;
  }, [ordersQ.data]);

  const opportunities: Opportunity[] | null = useMemo(() => {
    const data = oppsQ.data as { opportunities?: Opportunity[] } | null;
    if (!data) return null;
    return data.opportunities ?? [];
  }, [oppsQ.data]);

  const workingOrders = useMemo(() => {
    if (!orders || "unavailable" in orders) return [];
    return orders.filter(o => o.orderState === 'ROUTING' || o.orderState === 'PARTIAL' || o.orderState === 'VERIFYING');
  }, [orders]);

  if (instrumentsQ.loading) {
    return <div className="text-xs text-text-muted font-mono p-8">Loading instruments from /api/v1/market/instruments…</div>;
  }
  if (instrumentsQ.error || !instrumentsQ.data) {
    return <Unavailable title="Trading unavailable" reason={instrumentsQ.error ?? "no instruments payload"} />;
  }

  return (
    <div className="flex-1 flex flex-col space-y-3 font-mono text-xs select-none">
      {/* 1. TOP INSTRUMENT PICKER STRIP (symbols only — the feed publishes no quotes) */}
      <div className="bg-[var(--color-surface-0)] border border-border-strong rounded-xl p-2.5 flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          {/* Category Filter Pills */}
          <div className="flex items-center gap-1 overflow-x-auto py-0.5 max-w-full">
            <span className="text-[10px] text-text-muted font-bold uppercase mr-1 flex items-center gap-1">
              <Filter className="w-3 h-3 text-accent" />
              Markets:
            </span>
            {categories.map(cat => (
              <button
                key={cat}
                onClick={() => setActiveCategoryFilter(cat)}
                className={`px-2.5 py-1 rounded text-[10px] font-semibold whitespace-nowrap transition-all ${
                  activeCategoryFilter === cat
                    ? 'bg-info-bg text-accent border border-accent shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                    : 'text-text-muted hover:text-text-strong hover:bg-surface-veil'
                }`}
              >
                {cat === 'ALL' ? 'All Instruments' : cat}
              </button>
            ))}
          </div>

          {/* Quick Search & Settings Link */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-text-muted absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search symbol..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-[var(--color-surface-deep)] border border-border-subtle rounded pl-8 pr-2.5 py-1 text-text-strong text-[10px] w-56 outline-none focus:border-accent"
              />
            </div>

            {onOpenSettings && (
              <button
                onClick={onOpenSettings}
                className="px-2.5 py-1 rounded bg-surface-veil border border-border-subtle hover:bg-surface-raised text-text text-[10px] flex items-center gap-1.5 transition-all"
                title="Configure TradingView API and Datafeeds"
              >
                <SettingsIcon className="w-3 h-3 text-accent" />
                <span className="hidden sm:inline">TradingView API Settings</span>
              </button>
            )}
          </div>
        </div>

        {/* Horizontal Instrument Tape */}
        {filteredInstruments.length === 0 ? (
          <div className="py-6 text-center text-text-subtle text-[11px]">
            No instruments published. The backend reports an empty symbol list
            (no regimes, positions, or orders reference any symbol yet).
          </div>
        ) : (
          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
            {filteredInstruments.map(inst => {
              const isSelected = inst.symbol === activeSymbol;
              return (
                <button
                  key={inst.symbol}
                  onClick={() => setSelectedSymbol(inst.symbol)}
                  className={`flex items-center gap-2.5 px-3 py-1.5 rounded-lg border transition-all text-left flex-shrink-0 ${
                    isSelected
                      ? 'bg-info-bg border-accent shadow-[0_0_12px_rgba(0,240,255,0.15)] ring-1 ring-accent'
                      : 'bg-[var(--color-surface-2)] border-border-subtle hover:bg-surface-veil hover:border-border-subtle'
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-text-strong text-[11px]">{inst.symbol}</span>
                    </div>
                    <div className="text-[9px] text-text-subtle">
                      {inst.category || 'UNKNOWN'} • quote on chart
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* 2. MAIN TRADING TERMINAL GRID: CHART + TICKET + BOOK/TAPE */}
      {activeSymbol && (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-start">
          {/* LEFT / CENTER: CHART (8 Cols) */}
          <div className="xl:col-span-8 space-y-3">
            <TradingViewAdvancedChart
              symbol={activeSymbol}
              name={instruments.find(i => i.symbol === activeSymbol)?.name ?? activeSymbol}
              category={instruments.find(i => i.symbol === activeSymbol)?.category ?? 'UNKNOWN'}
              settings={settings}
              activePositions={positions && !("unavailable" in positions) ? positions : []}
              onOpenSettings={onOpenSettings}
              onMarkPrice={(m) => setMark(m ?? 0)}
            />
          </div>

          {/* RIGHT COLUMN: ORDER TICKET + BOOK / TAPE (4 Cols) */}
          <div className="xl:col-span-4 space-y-3">
            {/* Staging Order Ticket (submission not wired) */}
            <OrderExecutionTicket
              key={activeSymbol}
              symbol={activeSymbol}
              name={activeSymbol}
              category={instruments.find(i => i.symbol === activeSymbol)?.category ?? 'UNKNOWN'}
              markPrice={mark}
              settings={settings}
              onTriggerToast={onTriggerToast ?? (() => {})}
            />

            {/* L2 DOM Order Book & Time & Sales Tape in 2 Columns / Tabs */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <OrderBookDOM
                symbol={activeSymbol}
                markPrice={mark}
                onSelectPrice={(p) => {
                  if (onTriggerToast) onTriggerToast(`Selected Limit Price: $${p}`);
                }}
              />

              <TradeTapeTimeSales
                symbol={activeSymbol}
                markPrice={mark}
              />
            </div>
          </div>
        </div>
      )}

      {/* 3. BOTTOM PANEL: POSITIONS, WORKING ORDERS, EXECUTIONS, OPPORTUNITIES */}
      <div className="bg-[var(--color-surface-0)] border border-border-strong rounded-xl overflow-hidden font-mono text-xs">
        {/* Panel Tabs */}
        <div className="bg-[var(--color-surface-2)] border-b border-border-strong px-3.5 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {[
              { id: 'POSITIONS', label: `Open Positions (${positions && !("unavailable" in positions) ? positions.length : 0})`, icon: Layers },
              { id: 'WORKING_ORDERS', label: `Working Orders (${workingOrders.length})`, icon: Clock },
              { id: 'EXECUTION_TAPE', label: `Recent Executions (${orders && !("unavailable" in orders) ? orders.length : 0})`, icon: Zap },
              { id: 'AGENT_SIGNALS', label: `Opportunities`, icon: Layers }
            ].map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveBottomTab(tab.id as never)}
                  className={`px-3 py-1 rounded-lg text-[11px] font-semibold flex items-center gap-1.5 transition-all ${
                    activeBottomTab === tab.id
                      ? 'bg-info-bg text-accent border border-accent shadow-[0_0_8px_rgba(0,240,255,0.15)] font-bold'
                      : 'text-text-muted hover:text-text-strong hover:bg-surface-veil'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.label}
                </button>
              );
            })}
          </div>

          <div className="text-[10px] text-text-muted">
            Sources: /positions • /orders • /opportunities
          </div>
        </div>

        {/* Tab Content 1: Open Positions (live /positions) */}
        {activeBottomTab === 'POSITIONS' && (
          <div className="divide-y divide-surface-veil overflow-x-auto">
            {positionsQ.loading ? (
              <div className="py-8 text-center text-text-subtle">Loading positions…</div>
            ) : positionsQ.error || !positions ? (
              <div className="p-4"><Unavailable title="Positions unavailable" reason={positionsQ.error ?? "no positions payload"} /></div>
            ) : "unavailable" in positions ? (
              <div className="p-4"><Unavailable title="Positions unavailable" reason={positions.unavailable} /></div>
            ) : positions.length === 0 ? (
              <div className="py-8 text-center text-text-muted">
                No open positions reported by /api/v1/positions.
              </div>
            ) : (
              <table className="w-full text-left text-[11px]">
                <thead className="bg-surface-sunken text-[9px] uppercase font-bold text-text-muted">
                  <tr>
                    <th className="px-3.5 py-2">Symbol</th>
                    <th className="px-3 py-2">Side</th>
                    <th className="px-3 py-2">Size</th>
                    <th className="px-3 py-2">Entry Price</th>
                    <th className="px-3 py-2">Mark Price</th>
                    <th className="px-3 py-2">Notional (USD)</th>
                    <th className="px-3 py-2">Unrealized PnL</th>
                    <th className="px-3 py-2">Stop Loss</th>
                    <th className="px-3 py-2">Take Profit</th>
                    <th className="px-3.5 py-2 text-right">Inspect</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-veil">
                  {positions.map(pos => {
                    const isProfit = (pos.unrealizedPnlUsd || 0) >= 0;
                    return (
                      <tr key={pos.id} className="hover:bg-surface-veil transition-colors">
                        <td className="px-3.5 py-2 font-bold text-text-strong">
                          <button
                            onClick={() => setSelectedSymbol(pos.symbol)}
                            className="hover:text-accent underline font-mono"
                          >
                            {pos.symbol}
                          </button>
                        </td>
                        <td className="px-3 py-2">
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            pos.side === 'LONG' ? 'bg-positive-bg text-positive border border-positive' : 'bg-destructive-bg text-destructive border border-destructive'
                          }`}>
                            {pos.side}
                          </span>
                        </td>
                        <td className="px-3 py-2 font-mono-num text-text-strong">{pos.size.toLocaleString()}</td>
                        <td className="px-3 py-2 font-mono-num text-text">${pos.entryPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                        <td className="px-3 py-2 font-mono-num font-bold text-text-strong">${pos.markPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                        <td className="px-3 py-2 font-mono-num text-text">${pos.notionalUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                        <td className={`px-3 py-2 font-mono-num font-bold ${isProfit ? 'text-positive' : 'text-destructive'}`}>
                          {isProfit ? '+' : ''}${pos.unrealizedPnlUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })} ({pos.unrealizedPnlPct.toFixed(2)}%)
                        </td>
                        <td className="px-3 py-2 font-mono-num text-destructive">
                          {pos.stopLossPrice ? `$${pos.stopLossPrice.toLocaleString()}` : '—'}
                        </td>
                        <td className="px-3 py-2 font-mono-num text-positive">
                          {pos.takeProfitPrice ? `$${pos.takeProfitPrice.toLocaleString()}` : '—'}
                        </td>
                        <td className="px-3.5 py-2 text-right">
                          <button
                            onClick={() => onInspectPosition && onInspectPosition(pos)}
                            className="px-2 py-0.5 rounded bg-surface-veil hover:bg-surface-raised border border-border-strong text-text font-bold text-[9px] transition-all"
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Tab Content 2: Working Orders (live /orders) */}
        {activeBottomTab === 'WORKING_ORDERS' && (
          <div className="p-3.5">
            {ordersQ.loading ? (
              <div className="py-6 text-center text-text-subtle">Loading orders…</div>
            ) : ordersQ.error || !orders ? (
              <Unavailable title="Orders unavailable" reason={ordersQ.error ?? "no orders payload"} />
            ) : "unavailable" in orders ? (
              <Unavailable title="Orders unavailable" reason={orders.unavailable} />
            ) : workingOrders.length === 0 ? (
              <div className="py-6 text-center text-text-muted">
                No working orders reported by /api/v1/orders.
              </div>
            ) : (
              <div className="space-y-2">
                {workingOrders.map(ord => (
                  <div key={ord.id} className="bg-surface-sunken border border-border-subtle rounded-lg p-2.5 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-bold text-accent">{ord.id}</span>
                      <span className="text-text-strong">{ord.side} {ord.quantity.toLocaleString()} {ord.symbol}</span>
                      <span className="px-1.5 py-0.5 rounded bg-warning-bg text-warning text-[9px] border border-warning">
                        {ord.orderState}
                      </span>
                    </div>
                    <span className="text-[10px] text-text-subtle">cancel not wired</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab Content 3: Recent Executions (live /orders) */}
        {activeBottomTab === 'EXECUTION_TAPE' && (
          <div className="overflow-x-auto">
            {ordersQ.loading ? (
              <div className="py-6 text-center text-text-subtle">Loading orders…</div>
            ) : ordersQ.error || !orders ? (
              <div className="p-4"><Unavailable title="Orders unavailable" reason={ordersQ.error ?? "no orders payload"} /></div>
            ) : "unavailable" in orders ? (
              <div className="p-4"><Unavailable title="Orders unavailable" reason={orders.unavailable} /></div>
            ) : orders.length === 0 ? (
              <div className="py-6 text-center text-text-muted">
                No orders reported by /api/v1/orders.
              </div>
            ) : (
              <table className="w-full text-left text-[11px]">
                <thead className="bg-surface-sunken text-[9px] uppercase font-bold text-text-muted">
                  <tr>
                    <th className="px-3.5 py-2">Order ID</th>
                    <th className="px-3 py-2">Time</th>
                    <th className="px-3 py-2">Symbol</th>
                    <th className="px-3 py-2">Side</th>
                    <th className="px-3 py-2">Quantity</th>
                    <th className="px-3 py-2">Fill Price</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Reject Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-veil">
                  {orders.slice(0, 25).map(ord => (
                    <tr key={ord.id} className="hover:bg-surface-veil">
                      <td className="px-3.5 py-1.5 font-bold text-text">{ord.id}</td>
                      <td className="px-3 py-1.5 text-text-muted">{ord.time}</td>
                      <td className="px-3 py-1.5 font-bold text-text-strong">{ord.symbol}</td>
                      <td className="px-3 py-1.5">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                          ord.side === 'BUY' ? 'text-positive' : 'text-destructive'
                        }`}>
                          {ord.side}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 font-mono-num">{ord.quantity.toLocaleString()}</td>
                      <td className="px-3 py-1.5 font-mono-num font-bold text-text-strong">
                        {ord.fillPrice ? `$${ord.fillPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "—"}
                      </td>
                      <td className="px-3 py-1.5">
                        <span className="px-1.5 py-0.5 rounded bg-surface-veil text-text text-[9px] border border-border-subtle">
                          {ord.orderState}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 text-text-subtle text-[10px]">—</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Tab Content 4: Opportunities for symbol (live /opportunities) */}
        {activeBottomTab === 'AGENT_SIGNALS' && (
          <div className="p-3.5 space-y-2.5">
            {oppsQ.loading ? (
              <div className="py-6 text-center text-text-subtle">Loading opportunities…</div>
            ) : oppsQ.error || opportunities === null ? (
              <Unavailable title="Opportunities unavailable" reason={oppsQ.error ?? "no opportunities payload"} />
            ) : opportunities.length === 0 ? (
              <div className="py-6 text-center text-text-muted">
                No opportunities published by /api/v1/opportunities. No consensus stance is claimed.
              </div>
            ) : (
              opportunities
                .filter(o => !activeSymbol || !o.symbol || o.symbol === activeSymbol)
                .map(o => (
                  <div key={o.strategy_id} className="bg-surface-sunken border border-border-subtle rounded-lg p-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span className="font-bold text-text-strong text-xs">{o.strategy_id}</span>
                      <span className="text-[10px] text-text-muted ml-2">{o.family ?? "—"} • {o.symbol ?? "—"}</span>
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-text-muted font-mono-num">
                      <span>edge: <strong className="text-accent">{o.edge_proxy ?? "—"}</strong></span>
                      <span>exp R:R: <strong className="text-text-strong">{o.expected_rr ?? "—"}</strong></span>
                      <span>rank: <strong className="text-text-strong">{o.composite_rank ?? "—"}</strong></span>
                    </div>
                  </div>
                ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
