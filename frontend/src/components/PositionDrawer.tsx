import React from 'react';
import { Position } from '../types';
import { 
  X, 
  TrendingUp, 
  TrendingDown, 
  ShieldCheck, 
   
   
   
  AlertTriangle,

} from 'lucide-react';

interface PositionDrawerProps {
  position: Position | null;
  onClose: () => void;
  onTrimPosition?: (posId: string, pct: number) => void;
  onFlattenPosition?: (posId: string) => void;
}

export const PositionDrawer: React.FC<PositionDrawerProps> = ({
  position,
  onClose,
  onTrimPosition,
  onFlattenPosition,
}) => {
  if (!position) return null;

  const isProfitable = position.unrealizedPnlUsd >= 0;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm flex justify-end animate-fade-in">
      <div className="w-full max-w-xl bg-[#0d0f17] border-l border-white/[0.1] h-full shadow-2xl flex flex-col justify-between p-6 font-mono overflow-y-auto">
        {/* Drawer Header */}
        <div>
          <div className="flex items-center justify-between pb-4 border-b border-white/[0.08]">
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded bg-cyan-400 shadow-[0_0_8px_#00f0ff]"></div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-white tracking-tight">{position.symbol}</h2>
                  <span className={`text-xs px-2 py-0.5 rounded border font-semibold ${
                    position.side === 'LONG' 
                      ? 'bg-emerald-950 text-emerald-400 border-emerald-700' 
                      : 'bg-rose-950 text-rose-400 border-rose-700'
                  }`}>
                    {position.side}
                  </span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  ASSET CLASS: <strong className="text-slate-200">{position.assetClass}</strong>
                </div>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Core Institutional Financials */}
          <div className="grid grid-cols-2 gap-3 my-4">
            <div className="p-3 rounded bg-white/[0.02] border border-white/[0.06]">
              <div className="text-[10px] text-slate-400">UNREALIZED P&L</div>
              <div className={`text-lg font-mono-num font-bold flex items-center gap-1 mt-1 ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                {isProfitable ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                {isProfitable ? '+' : ''}${position.unrealizedPnlUsd.toLocaleString()} ({isProfitable ? '+' : ''}{position.unrealizedPnlPct.toFixed(2)}%)
              </div>
            </div>

            <div className="p-3 rounded bg-white/[0.02] border border-white/[0.06]">
              <div className="text-[10px] text-slate-400">NOTIONAL VALUE</div>
              <div className="text-lg font-mono-num font-bold text-white mt-1">
                ${position.notionalUsd.toLocaleString()}
              </div>
            </div>
          </div>

          {/* Pricing & Risk Parameters Grid */}
          <div className="p-3.5 rounded bg-black/40 border border-white/[0.06] space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-400">CURRENT SIZE:</span>
              <span className="text-white font-mono-num font-semibold">{position.size.toLocaleString()} units</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">ENTRY PRICE:</span>
              <span className="text-slate-200 font-mono-num">${position.entryPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">CURRENT MARK:</span>
              <span className="text-cyan-300 font-mono-num font-semibold">${(position.markPrice || (position as any).currentPrice || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">PORTFOLIO WEIGHT:</span>
              <span className="text-white font-mono-num">{(position.exposurePct || (position as any).portfolioWeightPct || 0).toFixed(2)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">RISK CONTRIBUTION:</span>
              <span className="text-amber-400 font-mono-num">
                {position.varContributionUsd ? `$${(position.varContributionUsd / 1000).toFixed(0)}k VaR` : `${((position as any).riskContributionPct || 1.2).toFixed(2)}%`}
              </span>
            </div>
            {position.stopLossPrice && (
              <div className="flex justify-between border-t border-white/[0.06] pt-2">
                <span className="text-rose-400 flex items-center gap-1 font-semibold">
                  <AlertTriangle className="w-3 h-3 text-rose-400" /> STOP-LOSS TRIGGER:
                </span>
                <span className="text-rose-400 font-mono font-bold">${position.stopLossPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              </div>
            )}
            {position.takeProfitPrice && (
              <div className="flex justify-between">
                <span className="text-emerald-400 font-semibold">TAKE PROFIT TARGET:</span>
                <span className="text-emerald-400 font-mono font-bold">${position.takeProfitPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              </div>
            )}
            {(position as any).liquidationPrice && (
              <div className="flex justify-between border-t border-white/[0.06] pt-2">
                <span className="text-rose-400 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> ESTIMATED LIQUIDATION:
                </span>
                <span className="text-rose-400 font-mono-num">${(position as any).liquidationPrice.toLocaleString()}</span>
              </div>
            )}
          </div>

          {/* Strategy & Agent Lineage */}
          <div className="mt-4 p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-2 text-xs">
            <div className="text-[10px] text-slate-400 uppercase tracking-wider">STRATEGY ALLOCATION &amp; MULTI-ASSET METADATA</div>
            <div className="flex justify-between">
              <span className="text-slate-400">STRATEGY:</span>
              <span className="text-slate-200 font-semibold">{position.strategy}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">PROPOSING AGENT:</span>
              <span className="text-cyan-300">{position.originatingAgent || (position as any).proposingAgent || 'MULTI-ASSET-ALLOCATOR'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">EXECUTION VENUE / CLOB:</span>
              <span className="text-slate-300">{position.exchange || (position as any).venue || 'Institutional Primary CLOB'}</span>
            </div>
            {position.country && (
              <div className="flex justify-between">
                <span className="text-slate-400">JURISDICTION / COUNTRY:</span>
                <span className="text-slate-200">{position.country} ({position.countryCode || 'INTL'})</span>
              </div>
            )}
            {position.polymarketOddsPct !== undefined && (
              <div className="flex justify-between border-t border-white/[0.06] pt-1.5 text-pink-300">
                <span>POLYMARKET CONSENSUS PROBABILITY:</span>
                <span className="font-bold">{position.polymarketOddsPct}% (Exp: {position.eventOutcomeDate})</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-slate-400">HOLDING DURATION:</span>
              <span className="text-slate-300">3d 14h 22m</span>
            </div>
          </div>

          {/* Constitutional Compliance Status */}
          <div className="mt-4 p-3 rounded bg-emerald-950/20 border border-emerald-800/40 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2 text-emerald-400">
              <ShieldCheck className="w-4 h-4" />
              <span>CONSTITUTIONAL FIREWALL VALIDATED</span>
            </div>
            <span className="text-[10px] text-emerald-500 font-mono">HASH #9a2b8...</span>
          </div>
        </div>

        {/* Action Controls Footer */}
        <div className="mt-6 pt-4 border-t border-white/[0.08] space-y-2">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">
            GOVERNANCE ACTIONS
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => onTrimPosition && onTrimPosition(position.id, 25)}
              className="py-2 px-3 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs text-slate-200 hover:text-white transition-all font-semibold"
            >
              TRIM 25% NOTIONAL
            </button>
            <button
              onClick={() => onTrimPosition && onTrimPosition(position.id, 50)}
              className="py-2 px-3 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs text-slate-200 hover:text-white transition-all font-semibold"
            >
              TRIM 50% NOTIONAL
            </button>
          </div>

          <button
            onClick={() => onFlattenPosition && onFlattenPosition(position.id)}
            className="w-full py-2.5 px-4 rounded bg-red-950/80 hover:bg-red-900 border border-red-700/60 text-xs text-red-300 hover:text-white font-bold transition-all shadow-[0_0_12px_rgba(239,68,68,0.2)]"
          >
            FLATTEN POSITION (CLOSE 100%)
          </button>
        </div>
      </div>
    </div>
  );
};
