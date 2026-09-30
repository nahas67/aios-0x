import React, { useState, useMemo } from 'react';
import { 
   
   
  Search, 
  Layers, 
   
  Zap, 
   
  Sparkles, 
   
  Clock, 
   
   
   
   
  
  
  Settings as SettingsIcon,
  Filter,
  
  

} from 'lucide-react';
import { Position, ExecutionOrder, SystemSettings } from '../../types';
import { TradingViewAdvancedChart } from '../trading/TradingViewAdvancedChart';
import { OrderBookDOM } from '../trading/OrderBookDOM';
import { TradeTapeTimeSales } from '../trading/TradeTapeTimeSales';
import { OrderExecutionTicket } from '../trading/OrderExecutionTicket';

interface LiveTradingWorkspaceProps {
  positions?: Position[];
  settings: SystemSettings;
  onAddOrder?: (order: ExecutionOrder) => void;
  onAddPosition?: (pos: Position) => void;
  onClosePosition?: (posId: string) => void;
  onOpenSettings?: () => void;
  onTriggerToast?: (msg: string) => void;
}

export interface TradableAsset {
  symbol: string;
  name: string;
  category: 'CRYPTO' | 'EQUITIES_US' | 'EQUITIES_GLOBAL' | 'POLYMARKET' | 'COMMODITIES' | 'FOREX';
  price: number;
  change24hPct: number;
  high24h: number;
  low24h: number;
  volume24h: string;
  fundingRateOrYield?: string;
  tvSymbol: string;
}

export const ALL_TRADABLE_ASSETS: TradableAsset[] = [
  // CRYPTO
  { symbol: 'BTC/USD', name: 'Bitcoin Network', category: 'CRYPTO', price: 94820.00, change24hPct: 2.34, high24h: 96100.00, low24h: 92450.00, volume24h: '$38.2B', fundingRateOrYield: '+0.0102% 8h', tvSymbol: 'BINANCE:BTCUSDT' },
  { symbol: 'ETH/USD', name: 'Ethereum Proof-of-Stake', category: 'CRYPTO', price: 3410.50, change24hPct: 3.82, high24h: 3480.00, low24h: 3260.00, volume24h: '$16.4B', fundingRateOrYield: '+0.0084% 8h', tvSymbol: 'BINANCE:ETHUSDT' },
  { symbol: 'SOL/USD', name: 'Solana High-Throughput', category: 'CRYPTO', price: 184.20, change24hPct: -1.15, high24h: 191.00, low24h: 179.50, volume24h: '$4.1B', fundingRateOrYield: '+0.0125% 8h', tvSymbol: 'BINANCE:SOLUSDT' },

  // US TECH & EQUITIES
  { symbol: 'NVDA', name: 'Nvidia Corp (Blackwell AI)', category: 'EQUITIES_US', price: 138.40, change24hPct: 3.14, high24h: 141.20, low24h: 135.00, volume24h: '$18.9B', tvSymbol: 'NASDAQ:NVDA' },
  { symbol: 'MSFT', name: 'Microsoft Corporation', category: 'EQUITIES_US', price: 428.50, change24hPct: 0.85, high24h: 432.00, low24h: 425.10, volume24h: '$7.8B', tvSymbol: 'NASDAQ:MSFT' },
  { symbol: 'AAPL', name: 'Apple Inc', category: 'EQUITIES_US', price: 232.10, change24hPct: -0.42, high24h: 234.50, low24h: 230.80, volume24h: '$6.9B', tvSymbol: 'NASDAQ:AAPL' },

  // GLOBAL EQUITIES
  { symbol: '7203.T', name: 'Toyota Motor Corp (TSE)', category: 'EQUITIES_GLOBAL', price: 2680.0, change24hPct: 1.45, high24h: 2710.0, low24h: 2640.0, volume24h: '¥142B', tvSymbol: 'TSE:7203' },
  { symbol: 'ASML.AS', name: 'ASML Holding N.V. (Euronext)', category: 'EQUITIES_GLOBAL', price: 742.80, change24hPct: 2.10, high24h: 755.00, low24h: 730.00, volume24h: '€2.4B', tvSymbol: 'EURONEXT:ASML' },
  { symbol: '0700.HK', name: 'Tencent Holdings (HKEX)', category: 'EQUITIES_GLOBAL', price: 412.40, change24hPct: -0.80, high24h: 420.00, low24h: 409.00, volume24h: 'HK$8.9B', tvSymbol: 'HKEX:700' },
  { symbol: 'RELIANCE.NS', name: 'Reliance Industries (NSE India)', category: 'EQUITIES_GLOBAL', price: 2940.0, change24hPct: 0.65, high24h: 2965.0, low24h: 2910.0, volume24h: '₹48B', tvSymbol: 'NSE:RELIANCE' },

  // COMMODITIES
  { symbol: 'XAU/USD', name: 'Spot Gold Bullion', category: 'COMMODITIES', price: 2735.40, change24hPct: 0.94, high24h: 2748.00, low24h: 2712.00, volume24h: '$24.5B', tvSymbol: 'TVC:GOLD' },
  { symbol: 'BRENT', name: 'Brent Crude Oil Futures', category: 'COMMODITIES', price: 74.80, change24hPct: -1.35, high24h: 76.20, low24h: 73.90, volume24h: '$14.1B', tvSymbol: 'TVC:UKOIL' },
  { symbol: 'HG-COPPER', name: 'High Grade Copper COMEX', category: 'COMMODITIES', price: 4.38, change24hPct: 1.82, high24h: 4.45, low24h: 4.29, volume24h: '$3.8B', tvSymbol: 'COMEX:HG1!' },

  // FOREX
  { symbol: 'EUR/USD', name: 'Euro / US Dollar', category: 'FOREX', price: 1.0845, change24hPct: -0.18, high24h: 1.0890, low24h: 1.0820, volume24h: '$110B', tvSymbol: 'FX:EURUSD' },
  { symbol: 'USD/JPY', name: 'US Dollar / Japanese Yen', category: 'FOREX', price: 154.20, change24hPct: 0.45, high24h: 154.80, low24h: 153.40, volume24h: '$84B', tvSymbol: 'FX:USDJPY' },
  { symbol: 'GBP/USD', name: 'British Pound / US Dollar', category: 'FOREX', price: 1.2980, change24hPct: 0.12, high24h: 1.3020, low24h: 1.2940, volume24h: '$48B', tvSymbol: 'FX:GBPUSD' },

  // POLYMARKET PREDICTION CONTRACTS
  { symbol: 'PM-FED-25BP-SEP', name: 'Polymarket: Fed 25bps Rate Cut in September', category: 'POLYMARKET', price: 0.88, change24hPct: 4.76, high24h: 0.92, low24h: 0.83, volume24h: '$32.4M', tvSymbol: 'POLYMARKET:FED-25BP' },
  { symbol: 'PM-AI-ACT-ENFORCE', name: 'Polymarket: EU AI Act Stringent Enforcement Q4', category: 'POLYMARKET', price: 0.64, change24hPct: -3.03, high24h: 0.69, low24h: 0.61, volume24h: '$14.8M', tvSymbol: 'POLYMARKET:AI-ACT' },
  { symbol: 'PM-BOJ-HIKE-DEC', name: 'Polymarket: Bank of Japan Hikes Rates Dec 2026', category: 'POLYMARKET', price: 0.42, change24hPct: 7.69, high24h: 0.46, low24h: 0.38, volume24h: '$9.2M', tvSymbol: 'POLYMARKET:BOJ-HIKE' }
];

export const LiveTradingWorkspace: React.FC<LiveTradingWorkspaceProps> = ({
  positions = [],
  settings,
  onAddOrder,
  onAddPosition,
  onClosePosition,
  onOpenSettings,
  onTriggerToast,
}) => {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTC/USD');
  const [activeCategoryFilter, setActiveCategoryFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeBottomTab, setActiveBottomTab] = useState<'POSITIONS' | 'WORKING_ORDERS' | 'EXECUTION_TAPE' | 'AGENT_SIGNALS'>('POSITIONS');

  // Find active selected asset
  const activeAsset = useMemo(() => {
    return ALL_TRADABLE_ASSETS.find(a => a.symbol === selectedSymbol) || ALL_TRADABLE_ASSETS[0];
  }, [selectedSymbol]);

  // Filtered Assets for the Watchlist Bar
  const filteredAssets = useMemo(() => {
    return ALL_TRADABLE_ASSETS.filter(asset => {
      const matchCat = activeCategoryFilter === 'ALL' || asset.category === activeCategoryFilter;
      const matchSearch = asset.symbol.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          asset.name.toLowerCase().includes(searchQuery.toLowerCase());
      return matchCat && matchSearch;
    });
  }, [activeCategoryFilter, searchQuery]);

  const openOrders: ExecutionOrder[] = [];

  const handleQuickOrder = (side: 'BUY' | 'SELL', price: number) => {
    const defaultQty = activeAsset.symbol.includes('BTC') ? 1.5 : 500;
    const notional = defaultQty * price;

    const newOrder: ExecutionOrder = {
      id: `ORD-QCK-${Math.floor(100000 + Math.random() * 900000)}`,
      time: new Date().toTimeString().substring(0, 8),
      symbol: activeAsset.symbol,
      side,
      quantity: defaultQty,
      notionalUsd: notional,
      orderState: 'FILLED',
      fillPrice: price,
      slippageBps: 0.5,
      strategy: 'QuickClick-SOR-0x',
      agent: 'MANUAL_OVERRIDE',
      riskState: 'COMPLIANT',
      venue: 'Direct L2 FIX'
    };

    if (onAddOrder) onAddOrder(newOrder);

    if (onAddPosition) {
      onAddPosition({
        id: `POS-QCK-${Date.now()}`,
        symbol: activeAsset.symbol,
        name: activeAsset.name,
        assetClass: (activeAsset.category as any) || 'EQUITY',
        side: side === 'BUY' ? 'LONG' : 'SHORT',
        size: defaultQty,
        entryPrice: price,
        markPrice: price,
        notionalUsd: notional,
        unrealizedPnlUsd: 0,
        unrealizedPnlPct: 0,
        exposurePct: 1.5,
        strategy: 'Quick Interactive Fill',
        originatingAgent: 'agent-exec',
        varContributionUsd: Math.round(notional * 0.015),
        liquidityTier: 'TIER-1 (DIRECT)',
        exchange: 'Direct FIX'
      });
    }

    if (onTriggerToast) {
      onTriggerToast(`✓ Instant Quick ${side} executed for ${defaultQty} ${activeAsset.symbol} @ $${price.toLocaleString()}`);
    }
  };

  return (
    <div className="flex-1 flex flex-col space-y-3 font-mono text-xs select-none">
      {/* 1. TOP ASSET TICKER & WATCHLIST STRIP */}
      <div className="bg-[#08090d] border border-white/[0.08] rounded-xl p-2.5 flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          {/* Category Filter Pills */}
          <div className="flex items-center gap-1 overflow-x-auto py-0.5 max-w-full">
            <span className="text-[10px] text-slate-400 font-bold uppercase mr-1 flex items-center gap-1">
              <Filter className="w-3 h-3 text-cyan-400" />
              Markets:
            </span>
            {[
              { id: 'ALL', label: 'All Instruments' },
              { id: 'CRYPTO', label: 'Crypto' },
              { id: 'EQUITIES_US', label: 'US Equities' },
              { id: 'EQUITIES_GLOBAL', label: 'Global (TSE/HKEX/Euronext)' },
              { id: 'COMMODITIES', label: 'Commodities' },
              { id: 'FOREX', label: 'Forex' },
              { id: 'POLYMARKET', label: 'Polymarket' }
            ].map(cat => (
              <button
                key={cat.id}
                onClick={() => setActiveCategoryFilter(cat.id)}
                className={`px-2.5 py-1 rounded text-[10px] font-semibold whitespace-nowrap transition-all ${
                  activeCategoryFilter === cat.id
                    ? 'bg-cyan-950 text-cyan-300 border border-cyan-600/60 shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          {/* Quick Search & Settings Link */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search symbol (e.g. BTC, NVDA, 7203)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-[#050608] border border-white/10 rounded pl-8 pr-2.5 py-1 text-slate-200 text-[10px] w-56 outline-none focus:border-cyan-500"
              />
            </div>

            {onOpenSettings && (
              <button
                onClick={onOpenSettings}
                className="px-2.5 py-1 rounded bg-white/[0.04] border border-white/10 hover:bg-white/[0.08] text-slate-300 text-[10px] flex items-center gap-1.5 transition-all"
                title="Configure TradingView API and Datafeeds"
              >
                <SettingsIcon className="w-3 h-3 text-cyan-400" />
                <span className="hidden sm:inline">TradingView API Settings</span>
              </button>
            )}
          </div>
        </div>

        {/* Horizontal Watchlist Ticker Tape */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
          {filteredAssets.map(asset => {
            const isSelected = asset.symbol === selectedSymbol;
            return (
              <button
                key={asset.symbol}
                onClick={() => setSelectedSymbol(asset.symbol)}
                className={`flex items-center gap-2.5 px-3 py-1.5 rounded-lg border transition-all text-left flex-shrink-0 ${
                  isSelected
                    ? 'bg-cyan-950/40 border-cyan-500/60 shadow-[0_0_12px_rgba(0,240,255,0.15)] ring-1 ring-cyan-500/40'
                    : 'bg-[#0b0d13] border-white/[0.06] hover:bg-white/[0.04] hover:border-white/15'
                }`}
              >
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-slate-100 text-[11px]">{asset.symbol}</span>
                    <span className="text-[9px] text-slate-400 truncate max-w-[90px]">{asset.name.split(' ')[0]}</span>
                  </div>
                  <div className="text-[10px] text-slate-300 font-mono-num font-semibold">
                    ${asset.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </div>
                </div>

                <div className={`text-[10px] font-bold flex items-center ${
                  asset.change24hPct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}>
                  {asset.change24hPct >= 0 ? '+' : ''}{asset.change24hPct.toFixed(2)}%
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. MAIN TRADING TERMINAL GRID: CHART + DOM + ORDER TICKET */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-start">
        {/* LEFT / CENTER: ADVANCED TRADINGVIEW / NATIVE INTERACTIVE CHART (8 Cols) */}
        <div className="xl:col-span-8 space-y-3">
          <TradingViewAdvancedChart
            symbol={activeAsset.symbol}
            name={activeAsset.name}
            category={activeAsset.category}
            price={activeAsset.price}
            change24hPct={activeAsset.change24hPct}
            high24h={activeAsset.high24h}
            low24h={activeAsset.low24h}
            volume24h={activeAsset.volume24h}
            settings={settings}
            activePositions={positions}
            onQuickOrder={handleQuickOrder}
            onOpenSettings={onOpenSettings}
          />
        </div>

        {/* RIGHT COLUMN: ORDER TICKET + DOM / TIME & SALES (4 Cols) */}
        <div className="xl:col-span-4 space-y-3">
          {/* Algorithmic Order Ticket */}
          <OrderExecutionTicket
            symbol={activeAsset.symbol}
            name={activeAsset.name}
            category={activeAsset.category}
            markPrice={activeAsset.price}
            settings={settings}
            onDispatchOrder={(ord) => {
              if (onAddOrder) onAddOrder(ord);
            }}
            onAddPosition={(pos) => {
              if (onAddPosition) onAddPosition(pos);
            }}
            onTriggerToast={onTriggerToast ?? (() => {})}
          />

          {/* L2 DOM Order Book & Time & Sales Tape in 2 Columns / Tabs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <OrderBookDOM
              symbol={activeAsset.symbol}
              markPrice={activeAsset.price}
              onSelectPrice={(p) => {
                if (onTriggerToast) onTriggerToast(`Selected Limit Price: $${p}`);
              }}
            />

            <TradeTapeTimeSales
              symbol={activeAsset.symbol}
              markPrice={activeAsset.price}
            />
          </div>
        </div>
      </div>

      {/* 3. BOTTOM PANEL: OPEN POSITIONS, WORKING ORDERS, RECENT EXECUTIONS, & AGENT SIGNALS */}
      <div className="bg-[#08090d] border border-white/[0.08] rounded-xl overflow-hidden font-mono text-xs">
        {/* Panel Tabs */}
        <div className="bg-[#0b0d13] border-b border-white/[0.08] px-3.5 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {[
              { id: 'POSITIONS', label: `Open Positions (${positions.length})`, icon: Layers },
              { id: 'WORKING_ORDERS', label: `Working Orders (${openOrders.filter(o => o.orderState === 'ROUTING' || o.orderState === 'PARTIAL' || o.orderState === 'VERIFYING').length})`, icon: Clock },
              { id: 'EXECUTION_TAPE', label: `Recent Executions (${openOrders.length})`, icon: Zap },
              { id: 'AGENT_SIGNALS', label: `Multi-Agent Signals (${activeAsset.symbol})`, icon: Sparkles }
            ].map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveBottomTab(tab.id as any)}
                  className={`px-3 py-1 rounded-lg text-[11px] font-semibold flex items-center gap-1.5 transition-all ${
                    activeBottomTab === tab.id
                      ? 'bg-cyan-950 text-cyan-300 border border-cyan-600/50 shadow-[0_0_8px_rgba(0,240,255,0.15)] font-bold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.label}
                </button>
              );
            })}
          </div>

          <div className="text-[10px] text-slate-400">
            Portfolio NAV: <strong className="text-slate-100 font-mono-num">—</strong>
          </div>
        </div>

        {/* Tab Content 1: Open Positions */}
        {activeBottomTab === 'POSITIONS' && (
          <div className="divide-y divide-white/[0.04] overflow-x-auto">
            {positions.length === 0 ? (
              <div className="py-8 text-center text-slate-400">
                No active open positions. Dispatch an order from the ticket above to establish exposure.
              </div>
            ) : (
              <table className="w-full text-left text-[11px]">
                <thead className="bg-black/30 text-[9px] uppercase font-bold text-slate-400">
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
                    <th className="px-3.5 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.02]">
                  {positions.map(pos => {
                    const isProfit = (pos.unrealizedPnlUsd || 0) >= 0;
                    return (
                      <tr key={pos.id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="px-3.5 py-2 font-bold text-slate-100 flex items-center gap-1.5">
                          <button 
                            onClick={() => setSelectedSymbol(pos.symbol)}
                            className="hover:text-cyan-300 underline font-mono"
                          >
                            {pos.symbol}
                          </button>
                          <span className="text-[9px] text-slate-400 font-normal">({pos.name})</span>
                        </td>
                        <td className="px-3 py-2">
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            pos.side === 'LONG' ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/40' : 'bg-rose-950 text-rose-300 border border-rose-700/40'
                          }`}>
                            {pos.side}
                          </span>
                        </td>
                        <td className="px-3 py-2 font-mono-num text-slate-200">{pos.size.toLocaleString()}</td>
                        <td className="px-3 py-2 font-mono-num text-slate-300">${pos.entryPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                        <td className="px-3 py-2 font-mono-num font-bold text-slate-100">${pos.markPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                        <td className="px-3 py-2 font-mono-num text-slate-300">${pos.notionalUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                        <td className={`px-3 py-2 font-mono-num font-bold ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {isProfit ? '+' : ''}${pos.unrealizedPnlUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })} ({pos.unrealizedPnlPct.toFixed(2)}%)
                        </td>
                        <td className="px-3 py-2 font-mono-num text-rose-300">
                          {pos.stopLossPrice ? `$${pos.stopLossPrice.toLocaleString()}` : '—'}
                        </td>
                        <td className="px-3 py-2 font-mono-num text-emerald-300">
                          {pos.takeProfitPrice ? `$${pos.takeProfitPrice.toLocaleString()}` : '—'}
                        </td>
                        <td className="px-3.5 py-2 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => {
                                if (onClosePosition) onClosePosition(pos.id);
                                if (onTriggerToast) onTriggerToast(`Closed position for ${pos.symbol}`);
                              }}
                              className="px-2 py-0.5 rounded bg-rose-950/70 hover:bg-rose-900 border border-rose-700/50 text-rose-200 font-bold text-[9px] transition-all"
                            >
                              Close
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Tab Content 2: Working Orders */}
        {activeBottomTab === 'WORKING_ORDERS' && (
          <div className="p-3.5">
            {openOrders.filter(o => o.orderState === 'ROUTING' || o.orderState === 'PARTIAL' || o.orderState === 'VERIFYING').length === 0 ? (
              <div className="py-6 text-center text-slate-400">
                No active working slices or pending limit orders. All recent algorithmic orders have completed execution.
              </div>
            ) : (
              <div className="space-y-2">
                {openOrders.filter(o => o.orderState === 'ROUTING' || o.orderState === 'PARTIAL' || o.orderState === 'VERIFYING').map(ord => (
                  <div key={ord.id} className="bg-black/30 border border-white/[0.06] rounded-lg p-2.5 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-bold text-cyan-300">{ord.id}</span>
                      <span className="text-slate-200">{ord.side} {ord.quantity.toLocaleString()} {ord.symbol}</span>
                      <span className="text-[10px] text-slate-400">Strategy: {ord.strategy}</span>
                      <span className="px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 text-[9px] border border-amber-800">
                        {ord.orderState}
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        if (onTriggerToast) onTriggerToast(`Order #${ord.id} cancelled`);
                      }}
                      className="px-2 py-0.5 rounded bg-rose-950 border border-rose-800 text-rose-300 text-[9px]"
                    >
                      Cancel Order
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab Content 3: Recent Executions */}
        {activeBottomTab === 'EXECUTION_TAPE' && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead className="bg-black/30 text-[9px] uppercase font-bold text-slate-400">
                <tr>
                  <th className="px-3.5 py-2">Order ID</th>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">Side</th>
                  <th className="px-3 py-2">Quantity</th>
                  <th className="px-3 py-2">Fill Price</th>
                  <th className="px-3 py-2">Slippage (bps)</th>
                  <th className="px-3 py-2">Venue</th>
                  <th className="px-3.5 py-2">Risk State</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.02]">
                {openOrders.slice(0, 10).map(ord => (
                  <tr key={ord.id} className="hover:bg-white/[0.02]">
                    <td className="px-3.5 py-1.5 font-bold text-slate-300">{ord.id}</td>
                    <td className="px-3 py-1.5 text-slate-400">{ord.time}</td>
                    <td className="px-3 py-1.5 font-bold text-slate-100">{ord.symbol}</td>
                    <td className="px-3 py-1.5">
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                        ord.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {ord.side}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 font-mono-num">{ord.quantity.toLocaleString()}</td>
                    <td className="px-3 py-1.5 font-mono-num font-bold text-slate-200">
                      ${ord.fillPrice?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="px-3 py-1.5 font-mono-num text-cyan-300">{ord.slippageBps} bps</td>
                    <td className="px-3 py-1.5 text-slate-400 text-[10px]">{ord.venue || 'Direct SOR'}</td>
                    <td className="px-3.5 py-1.5">
                      <span className="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 text-[9px] border border-emerald-800/40">
                        {ord.riskState}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab Content 4: Multi-Agent Signals for Symbol */}
        {activeBottomTab === 'AGENT_SIGNALS' && (
          <div className="p-3.5 space-y-2.5">
            <div className="bg-cyan-950/30 border border-cyan-800/40 rounded-lg p-3 flex items-start gap-3">
              <Sparkles className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" />
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-bold text-slate-100 text-xs">Consensus Stance: OVERWEIGHT / ACCUMULATE</span>
                  <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 text-[9px] font-bold border border-emerald-700">
                    Confidence: 91.4%
                  </span>
                </div>
                <p className="text-[11px] text-slate-300 leading-relaxed font-sans">
                  The multi-agent network (Macro, Fundamental, and Quantitative Alpha specialists) resolved a bullish consensus for <strong>{activeAsset.symbol}</strong>. The Adversarial Challenger tested downside liquidity against a 15% shock, confirming stop loss support at -4.5%. Deterministic risk firewall has pre-authorized allocation up to $15,000,000 notional.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
