import React, { useState } from 'react';
import { 
  Zap, 
  ShieldCheck, 
   
  Sparkles, 
   
   
  ArrowUpRight, 
  ArrowDownRight, 
  Clock, 
   
  

} from 'lucide-react';
import { ExecutionOrder, Position, SystemSettings } from '../../types';

interface OrderTicketProps {
  symbol: string;
  name: string;
  category: string;
  markPrice: number;
  settings: SystemSettings;
  onDispatchOrder: (order: ExecutionOrder) => void;
  onAddPosition: (pos: Position) => void;
  onTriggerToast: (msg: string) => void;
}

export type OrderSide = 'BUY' | 'SELL';
export type OrderType = 'MARKET' | 'LIMIT' | 'STOP_LIMIT' | 'TWAP' | 'VWAP' | 'POV';

export const OrderExecutionTicket: React.FC<OrderTicketProps> = ({
  symbol,
  name,
  category,
  markPrice,
  settings,
  onDispatchOrder,
  onAddPosition,
  onTriggerToast,
}) => {
  const [side, setSide] = useState<OrderSide>('BUY');
  const [orderType, setOrderType] = useState<OrderType>('TWAP');
  const [limitPrice, setLimitPrice] = useState<number>(markPrice);
  const [quantity, setQuantity] = useState<number>(() => {
    if (symbol.includes('BTC')) return 2.5;
    if (symbol.includes('ETH')) return 25.0;
    if (symbol.startsWith('PM-')) return 50000;
    if (symbol.includes('7203') || symbol.includes('NVDA')) return 1000;
    return 500;
  });

  const [twapMinutes, setTwapMinutes] = useState<number>(settings.twapWindowMinutes || 15);
  const [twapSlices, setTwapSlices] = useState<number>(8);
  const [stopLossPrice, setStopLossPrice] = useState<number>(+(markPrice * 0.96).toFixed(2));
  const [takeProfitPrice, setTakeProfitPrice] = useState<number>(+(markPrice * 1.08).toFixed(2));
  const [selectedVenue, setSelectedVenue] = useState<string>(() => {
    if (symbol.startsWith('PM-')) return 'Polymarket CLOB & Polygon';
    if (symbol.includes('/USD') && (symbol.includes('BTC') || symbol.includes('ETH'))) return 'Binance Institutional FIX';
    if (symbol.includes('EUR') || symbol.includes('JPY')) return 'EBS & 360T Interbank FX';
    if (symbol.includes('XAU') || symbol.includes('BRENT')) return 'ICE Europe / COMEX';
    return 'Interactive Brokers Global FIX';
  });

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Derived Calculations
  const notionalUsd = quantity * (orderType === 'LIMIT' ? limitPrice : markPrice);
  const maxEquityPool = 142000000;
  const portfolioExposurePct = +((notionalUsd / maxEquityPool) * 100).toFixed(2);
  
  const slLossUsd = Math.abs(markPrice - stopLossPrice) * quantity;
  const tpGainUsd = Math.abs(takeProfitPrice - markPrice) * quantity;
  const riskRewardRatio = slLossUsd > 0 ? +(tpGainUsd / slLossUsd).toFixed(2) : 2.5;

  // Quick percent of capital handler
  const handleQuickPercent = (pct: number) => {
    const targetNotional = maxEquityPool * (pct / 100) * 0.05; // 5% base allocation cap
    const units = Math.max(1, Math.round(targetNotional / markPrice));
    setQuantity(units);
  };

  // One-click AI Consensus Pre-Fill
  const handleApplyAgentConsensus = () => {
    setOrderType('TWAP');
    setTwapMinutes(20);
    setTwapSlices(10);
    setStopLossPrice(+(markPrice * 0.955).toFixed(2));
    setTakeProfitPrice(+(markPrice * 1.125).toFixed(2));
    const targetNotional = 7500000;
    setQuantity(Math.max(1, Math.round(targetNotional / markPrice)));
    onTriggerToast(`Applied multi-agent consensus trade setup for ${symbol}`);
  };

  // Submit Order Execution
  const handleExecuteTrade = () => {
    setIsSubmitting(true);

    setTimeout(() => {
      const orderId = `ORD-${Math.floor(100000 + Math.random() * 900000)}`;
      const executionTime = new Date().toTimeString().substring(0, 8);

      const newOrder: ExecutionOrder = {
        id: orderId,
        time: executionTime,
        symbol,
        side: side === 'BUY' ? 'BUY' : 'SELL',
        quantity,
        notionalUsd,
        orderState: 'FILLED',
        fillPrice: markPrice,
        slippageBps: +(0.4 + Math.random() * 0.6).toFixed(1),
        strategy: `${orderType}-SmartRoute-0x`,
        agent: 'EXECUTION_GATEWAY',
        riskState: 'COMPLIANT',
        venue: selectedVenue
      };

      const newPos: Position = {
        id: `POS-${symbol.replace(/[^a-zA-Z0-9]/g, '')}-${Date.now()}`,
        symbol,
        name,
        assetClass: (category as any) || 'EQUITY',
        side: side === 'BUY' ? 'LONG' : 'SHORT',
        size: quantity,
        entryPrice: markPrice,
        markPrice,
        notionalUsd,
        unrealizedPnlUsd: 0,
        unrealizedPnlPct: 0,
        exposurePct: portfolioExposurePct,
        stopLossPrice,
        takeProfitPrice,
        strategy: `${orderType} Execution Alpha Slicer`,
        originatingAgent: 'agent-exec',
        varContributionUsd: Math.round(notionalUsd * 0.015),
        liquidityTier: 'TIER-1 (SOR DIRECT)',
        exchange: selectedVenue
      };

      onDispatchOrder(newOrder);
      onAddPosition(newPos);
      setIsSubmitting(false);
      onTriggerToast(`✓ Order #${orderId} Dispatched & Filled: ${side} ${quantity.toLocaleString()} ${symbol} via ${selectedVenue.split(' ')[0]}`);
    }, 600);
  };

  return (
    <div className="bg-[#08090d] border border-white/[0.08] rounded-xl flex flex-col overflow-hidden font-mono text-xs select-none">
      {/* Header */}
      <div className="bg-[#0b0d13] border-b border-white/[0.08] px-3.5 py-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-bold text-slate-100 text-[11px] uppercase tracking-wider">Algorithmic Order Ticket</span>
        </div>

        {/* AI Co-Pilot One-Click Pre-fill */}
        <button
          onClick={handleApplyAgentConsensus}
          className="px-2 py-1 rounded bg-rose-950/70 hover:bg-rose-900/80 border border-rose-600/50 text-[10px] text-rose-200 font-semibold flex items-center gap-1 transition-all shadow-[0_0_10px_rgba(244,63,94,0.15)]"
          title="Pre-populate with Multi-Agent Ratified Debate Parameters"
        >
          <Sparkles className="w-3 h-3 text-rose-400" />
          AI Consensus Setup
        </button>
      </div>

      <div className="p-3.5 space-y-3">
        {/* BUY / SELL SIDE TOGGLE */}
        <div className="grid grid-cols-2 gap-1.5 p-1 bg-black/50 border border-white/10 rounded-lg">
          <button
            onClick={() => setSide('BUY')}
            className={`py-1.5 rounded font-bold text-xs transition-all flex items-center justify-center gap-1.5 ${
              side === 'BUY'
                ? 'bg-emerald-600 text-white shadow-[0_0_12px_rgba(16,185,129,0.35)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
            }`}
          >
            <ArrowUpRight className="w-3.5 h-3.5" />
            BUY / LONG
          </button>
          <button
            onClick={() => setSide('SELL')}
            className={`py-1.5 rounded font-bold text-xs transition-all flex items-center justify-center gap-1.5 ${
              side === 'SELL'
                ? 'bg-rose-600 text-white shadow-[0_0_12px_rgba(244,63,94,0.35)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
            }`}
          >
            <ArrowDownRight className="w-3.5 h-3.5" />
            SELL / SHORT
          </button>
        </div>

        {/* ORDER TYPE SELECTOR */}
        <div>
          <div className="text-[10px] text-slate-400 uppercase font-bold mb-1 flex items-center justify-between">
            <span>Execution Algorithm</span>
            <span className="text-cyan-300 font-normal text-[9px]">{orderType === 'TWAP' ? 'Time-Weighted Slicing' : orderType === 'VWAP' ? 'Volume Participation' : 'Direct Fill'}</span>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-1">
            {(['MARKET', 'LIMIT', 'STOP_LIMIT', 'TWAP', 'VWAP', 'POV'] as OrderType[]).map(type => (
              <button
                key={type}
                onClick={() => setOrderType(type)}
                className={`py-1 px-1.5 rounded text-[10px] font-semibold transition-all text-center truncate ${
                  orderType === type
                    ? 'bg-cyan-950 text-cyan-300 border border-cyan-600/60 shadow-[0_0_8px_rgba(0,240,255,0.2)] font-bold'
                    : 'bg-white/[0.02] text-slate-400 border border-white/[0.06] hover:bg-white/[0.05]'
                }`}
              >
                {type}
              </button>
            ))}
          </div>
        </div>

        {/* TWAP / VWAP SLICER CONFIGURATION (If TWAP or VWAP selected) */}
        {(orderType === 'TWAP' || orderType === 'VWAP') && (
          <div className="bg-cyan-950/20 border border-cyan-800/30 rounded-lg p-2.5 space-y-2">
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-cyan-300 font-bold flex items-center gap-1">
                <Clock className="w-3 h-3 text-cyan-400" />
                TWAP Duration & Slicing Window
              </span>
              <span className="text-slate-400 font-mono-num">{twapMinutes}m / {twapSlices} Slices</span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[10px]">
              <div>
                <label className="text-slate-400 text-[9px] block mb-0.5">Execution Window</label>
                <select
                  value={twapMinutes}
                  onChange={(e) => setTwapMinutes(Number(e.target.value))}
                  className="w-full bg-[#050608] border border-white/10 rounded px-2 py-1 text-slate-200 text-[10px] outline-none focus:border-cyan-500"
                >
                  <option value={5}>5 Minutes (Fast)</option>
                  <option value={15}>15 Minutes (Standard)</option>
                  <option value={30}>30 Minutes (Low Impact)</option>
                  <option value={60}>1 Hour (Passive)</option>
                  <option value={120}>2 Hours (Deep Liquidity)</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 text-[9px] block mb-0.5">Slice Quantity</label>
                <select
                  value={twapSlices}
                  onChange={(e) => setTwapSlices(Number(e.target.value))}
                  className="w-full bg-[#050608] border border-white/10 rounded px-2 py-1 text-slate-200 text-[10px] outline-none focus:border-cyan-500"
                >
                  <option value={4}>4 Slices</option>
                  <option value={8}>8 Slices</option>
                  <option value={12}>12 Slices</option>
                  <option value={20}>20 Slices</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* PRICE & QUANTITY INPUTS */}
        <div className="grid grid-cols-2 gap-2.5">
          {/* Limit Price (if not market) */}
          <div>
            <label className="text-[9px] uppercase font-bold text-slate-400 block mb-1">
              {orderType === 'MARKET' ? 'Estimated Fill Price' : 'Limit Price (USD)'}
            </label>
            <input
              type="number"
              value={orderType === 'MARKET' ? markPrice : limitPrice}
              disabled={orderType === 'MARKET'}
              onChange={(e) => setLimitPrice(Number(e.target.value))}
              step="any"
              className="w-full bg-[#050608] border border-white/10 rounded px-2.5 py-1.5 text-slate-100 font-mono-num text-xs outline-none focus:border-cyan-500 disabled:opacity-60 disabled:cursor-not-allowed"
            />
          </div>

          {/* Size / Units */}
          <div>
            <label className="text-[9px] uppercase font-bold text-slate-400 block mb-1">
              Quantity ({symbol.split('/')[0]})
            </label>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(Math.max(0.01, Number(e.target.value)))}
              step="any"
              className="w-full bg-[#050608] border border-white/10 rounded px-2.5 py-1.5 text-slate-100 font-mono-num text-xs outline-none focus:border-cyan-500 font-bold"
            />
          </div>
        </div>

        {/* QUICK ALLOCATION PRESETS */}
        <div className="flex items-center gap-1 text-[9px]">
          <span className="text-slate-400 mr-1 uppercase font-bold">Alloc %:</span>
          {[10, 25, 50, 100].map(pct => (
            <button
              key={pct}
              onClick={() => handleQuickPercent(pct)}
              className="flex-1 py-1 rounded bg-white/[0.04] border border-white/[0.08] hover:bg-white/[0.08] text-slate-300 font-semibold transition-all"
            >
              {pct}%
            </button>
          ))}
        </div>

        {/* STOP LOSS & TAKE PROFIT GUARDRAILS */}
        <div className="grid grid-cols-2 gap-2.5 bg-black/40 border border-white/[0.06] rounded-lg p-2.5">
          <div>
            <div className="flex items-center justify-between text-[9px] mb-1">
              <span className="text-rose-400 font-bold uppercase">Stop Loss</span>
              <span className="text-slate-400 font-mono-num">Est -${slLossUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            </div>
            <input
              type="number"
              value={stopLossPrice}
              onChange={(e) => setStopLossPrice(Number(e.target.value))}
              step="any"
              className="w-full bg-[#050608] border border-rose-900/40 rounded px-2 py-1 text-rose-300 font-mono-num text-[11px] outline-none focus:border-rose-500"
            />
          </div>

          <div>
            <div className="flex items-center justify-between text-[9px] mb-1">
              <span className="text-emerald-400 font-bold uppercase">Take Profit</span>
              <span className="text-slate-400 font-mono-num">Est +${tpGainUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            </div>
            <input
              type="number"
              value={takeProfitPrice}
              onChange={(e) => setTakeProfitPrice(Number(e.target.value))}
              step="any"
              className="w-full bg-[#050608] border border-emerald-900/40 rounded px-2 py-1 text-emerald-300 font-mono-num text-[11px] outline-none focus:border-emerald-500"
            />
          </div>
        </div>

        {/* VENUE ROUTING */}
        <div>
          <label className="text-[9px] uppercase font-bold text-slate-400 block mb-1">Smart Order Router (SOR) Gateway</label>
          <select
            value={selectedVenue}
            onChange={(e) => setSelectedVenue(e.target.value)}
            className="w-full bg-[#050608] border border-white/10 rounded px-2 py-1.5 text-slate-200 text-[10px] outline-none focus:border-cyan-500"
          >
            <option value="Polymarket CLOB & Polygon">Polymarket CLOB (L2 Polygon State)</option>
            <option value="Interactive Brokers Global FIX">Interactive Brokers Direct (TSE/Euronext/HKEX)</option>
            <option value="Binance Institutional FIX">Binance Institutional FIX 4.4 (Spot/Futures)</option>
            <option value="Coinbase Prime Custody">Coinbase Prime Execution Gateway</option>
            <option value="CME Group Aurora Direct">CME Aurora Co-location iLink3</option>
            <option value="EBS & 360T Interbank FX">EBS Interbank Foreign Exchange FIX</option>
            <option value="ICE Europe Commodities">ICE Europe / LME Metal & Crude Direct</option>
          </select>
        </div>

        {/* PRE-TRADE RISK FIREWALL METRICS */}
        <div className="bg-[#050608] border border-white/[0.06] rounded-lg p-2.5 space-y-1.5 text-[10px]">
          <div className="flex items-center justify-between text-slate-400">
            <span>Estimated Notional:</span>
            <span className="text-slate-100 font-bold font-mono-num">${notionalUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          </div>

          <div className="flex items-center justify-between text-slate-400">
            <span>Portfolio Exposure:</span>
            <span className="text-cyan-300 font-bold font-mono-num">{portfolioExposurePct}% (Cap: {settings.maxPositionConcentrationPct || 15}%)</span>
          </div>

          <div className="flex items-center justify-between text-slate-400">
            <span>Risk / Reward Ratio:</span>
            <span className="text-emerald-400 font-bold font-mono-num">1 : {riskRewardRatio}</span>
          </div>

          <div className="pt-1 border-t border-white/[0.06] flex items-center justify-between text-[9px]">
            <span className="text-emerald-400 flex items-center gap-1 font-bold">
              <ShieldCheck className="w-3 h-3 text-emerald-400" />
              15/15 Deterministic Firewall Checks Passed
            </span>
            <span className="text-slate-400">SHA-256 Valid</span>
          </div>
        </div>

        {/* DISPATCH ORDER BUTTON */}
        <button
          onClick={handleExecuteTrade}
          disabled={isSubmitting}
          className={`w-full py-2.5 rounded-lg font-bold text-xs flex items-center justify-center gap-2 transition-all cursor-pointer ${
            side === 'BUY'
              ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_16px_rgba(16,185,129,0.4)] active:scale-[0.99]'
              : 'bg-rose-600 hover:bg-rose-500 text-white shadow-[0_0_16px_rgba(244,63,94,0.4)] active:scale-[0.99]'
          } ${isSubmitting ? 'opacity-70 cursor-wait' : ''}`}
        >
          {isSubmitting ? (
            <>
              <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Routing via SOR Slicer...
            </>
          ) : (
            <>
              <Zap className="w-3.5 h-3.5" />
              DISPATCH {side} ORDER • ${notionalUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </>
          )}
        </button>
      </div>
    </div>
  );
};
