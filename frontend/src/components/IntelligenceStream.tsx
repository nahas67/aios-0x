import React, { useState } from 'react';
import { IntelligenceItem } from '../types';
import { 
  BrainCircuit, 
   
   
   
   
   
  RefreshCw,

} from 'lucide-react';

interface IntelligenceStreamProps {
  items: IntelligenceItem[];
  onSelectItem: (item: IntelligenceItem) => void;
  className?: string;
  /** Real refetch wired by the parent (useApi refresh). Spinner tracks it. */
  onRefresh?: () => void;
  refreshing?: boolean;
}

export const IntelligenceStream: React.FC<IntelligenceStreamProps> = ({
  items,
  onSelectItem,
  className = '',
  onRefresh,
  refreshing = false,
}) => {
  const [filter, setFilter] = useState<'ALL' | 'CRYPTO' | 'EQUITIES' | 'MACRO' | 'VOLATILITY'>('ALL');

  const filteredItems = filter === 'ALL'
    ? items
    : items.filter(i => i.category === filter);

  const handleRefresh = () => {
    if (onRefresh) onRefresh();
  };

  const getRiskBadge = (risk: IntelligenceItem['riskImpact']) => {
    switch (risk) {
      case 'LOW':
        return 'text-emerald-400 bg-emerald-950/40 border-emerald-800/40';
      case 'MEDIUM':
        return 'text-amber-400 bg-amber-950/40 border-amber-800/40';
      case 'HIGH':
      case 'CRITICAL':
        return 'text-red-400 bg-red-950/40 border-red-800/40 animate-pulse';
    }
  };

  const getActionBadge = (action: IntelligenceItem['action']) => {
    switch (action) {
      case 'WATCH':
        return 'text-cyan-400 bg-cyan-950/50 border-cyan-800/50';
      case 'ACCUMULATE':
        return 'text-emerald-300 bg-emerald-950/60 border-emerald-600/60 font-semibold';
      case 'TRIM':
        return 'text-amber-300 bg-amber-950/60 border-amber-600/60';
      case 'REBALANCE':
        return 'text-violet-300 bg-violet-950/60 border-violet-600/60';
      case 'HEDGE':
        return 'text-rose-300 bg-rose-950/60 border-rose-600/60 font-semibold';
    }
  };

  return (
    <div className={`bg-[#0d0f17] border border-white/[0.08] rounded-md p-3.5 flex flex-col justify-between shadow-2xl ${className}`}>
      {/* Stream Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-slate-100 uppercase">
            INVESTMENT INTELLIGENCE
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/50">
            MULTI-AGENT STREAM
          </span>
        </div>

        <button
          onClick={handleRefresh}
          disabled={!onRefresh}
          className="text-slate-400 hover:text-slate-200 p-1 rounded hover:bg-white/[0.04] transition-colors disabled:opacity-40"
          title={onRefresh ? "Refetch opportunities from /api/v1/opportunities" : "No refetch source"}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-cyan-400' : ''}`} />
        </button>
      </div>

      {/* Category Pills */}
      <div className="flex items-center gap-1.5 py-2 overflow-x-auto text-[10px] font-mono">
        {(['ALL', 'CRYPTO', 'EQUITIES', 'MACRO', 'VOLATILITY'] as const).map(cat => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`px-2 py-0.5 rounded transition-all whitespace-nowrap ${
              filter === cat
                ? 'bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 font-medium'
                : 'text-slate-400 hover:text-slate-200 bg-white/[0.02] border border-white/[0.05]'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Intelligence Cards Feed */}
      <div className="space-y-2 overflow-y-auto flex-1 max-h-[580px] pr-1">
        {filteredItems.map(item => (
          <div
            key={item.id}
            onClick={() => onSelectItem(item)}
            className="group p-2.5 rounded bg-white/[0.02] hover:bg-white/[0.05] border border-white/[0.06] hover:border-cyan-500/30 transition-all cursor-pointer relative"
          >
            {/* Top row: Category & Timestamp */}
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 pb-1">
              <span className="text-cyan-400/80 uppercase">{item.category}</span>
              <span>{item.timestamp}</span>
            </div>

            {/* Headline */}
            <h4 className="text-[12px] font-medium text-slate-200 group-hover:text-cyan-200 transition-colors leading-snug">
              {item.headline}
            </h4>

            {/* Detail */}
            <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
              {item.detail}
            </p>

            {/* Metrics Matrix Strip */}
            <div className="mt-2.5 pt-2 border-t border-white/[0.05] grid grid-cols-4 gap-2 text-center text-[10px] font-mono">
              <div className="bg-black/30 p-1 rounded border border-white/[0.04]">
                <div className="text-slate-500 text-[8px] uppercase tracking-wider">CONFIDENCE</div>
                <div className="font-mono-num font-semibold text-cyan-300">
                  {item.confidencePct.toFixed(1)}%
                </div>
              </div>

              <div className="bg-black/30 p-1 rounded border border-white/[0.04]">
                <div className="text-slate-500 text-[8px] uppercase tracking-wider">SUPPORT</div>
                <div className="font-mono-num font-semibold text-emerald-400">
                  {item.supportAgents} agts
                </div>
              </div>

              <div className="bg-black/30 p-1 rounded border border-white/[0.04]">
                <div className="text-slate-500 text-[8px] uppercase tracking-wider">COUNTER</div>
                <div className="font-mono-num font-semibold text-slate-400">
                  {item.counterAgents} agts
                </div>
              </div>

              <div className="bg-black/30 p-1 rounded border border-white/[0.04]">
                <div className="text-slate-500 text-[8px] uppercase tracking-wider">RISK</div>
                <div className={`font-mono-num font-semibold rounded px-0.5 border ${getRiskBadge(item.riskImpact)}`}>
                  {item.riskImpact}
                </div>
              </div>
            </div>

            {/* Action Footer */}
            <div className="mt-2 flex items-center justify-between text-[10px] font-mono">
              <span className="text-slate-500">RECOMMENDED ACTION:</span>
              <span className={`px-2 py-0.5 rounded border text-[10px] tracking-wide uppercase ${getActionBadge(item.action)}`}>
                {item.action}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Footer Info */}
      <div className="pt-2.5 mt-2 border-t border-white/[0.06] text-[10px] font-mono text-slate-500 flex items-center justify-between">
        <span>GATEWAY: QDRANT VECTOR MEMORY</span>
        <span className="text-emerald-400 flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
          ACTIVE LISTENER
        </span>
      </div>
    </div>
  );
};
