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
        return 'text-positive bg-positive-bg border-positive';
      case 'MEDIUM':
        return 'text-warning bg-warning-bg border-warning';
      case 'HIGH':
      case 'CRITICAL':
        return 'text-destructive bg-destructive border-destructive animate-pulse';
    }
  };

  const getActionBadge = (action: IntelligenceItem['action']) => {
    switch (action) {
      case 'WATCH':
        return 'text-accent bg-info-bg border-accent';
      case 'ACCUMULATE':
        return 'text-positive bg-positive-bg border-positive font-semibold';
      case 'TRIM':
        return 'text-warning bg-warning-bg border-warning';
      case 'REBALANCE':
        return 'text-violet bg-violet border-violet';
      case 'HEDGE':
        return 'text-destructive bg-destructive-bg border-destructive font-semibold';
    }
  };

  return (
    <div className={`bg-[var(--color-surface-1)] border border-border-strong rounded-md p-3.5 flex flex-col justify-between shadow-2xl ${className}`}>
      {/* Stream Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-text-strong uppercase">
            INVESTMENT INTELLIGENCE
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
            MULTI-AGENT STREAM
          </span>
        </div>

        <button
          onClick={handleRefresh}
          disabled={!onRefresh}
          className="text-text-muted hover:text-text-strong p-1 rounded hover:bg-surface-veil transition-colors disabled:opacity-40"
          title={onRefresh ? "Refetch opportunities from /api/v1/opportunities" : "No refetch source"}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-accent' : ''}`} />
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
                ? 'bg-info-bg text-accent border border-accent font-medium'
                : 'text-text-muted hover:text-text-strong bg-surface-veil border border-border-subtle'
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
            className="group p-2.5 rounded bg-surface-veil hover:bg-surface-raised border border-border-subtle hover:border-accent transition-all cursor-pointer relative"
          >
            {/* Top row: Category & Timestamp */}
            <div className="flex items-center justify-between text-[10px] font-mono text-text-subtle pb-1">
              <span className="text-accent uppercase">{item.category}</span>
              <span>{item.timestamp}</span>
            </div>

            {/* Headline */}
            <h4 className="text-[12px] font-medium text-text-strong group-hover:text-accent transition-colors leading-snug">
              {item.headline}
            </h4>

            {/* Detail */}
            <p className="text-[11px] text-text-muted mt-1 line-clamp-2 leading-relaxed">
              {item.detail}
            </p>

            {/* Metrics Matrix Strip */}
            <div className="mt-2.5 pt-2 border-t border-border-subtle grid grid-cols-4 gap-2 text-center text-[10px] font-mono">
              <div className="bg-surface-sunken p-1 rounded border border-border-subtle">
                <div className="text-text-subtle text-[8px] uppercase tracking-wider">CONFIDENCE</div>
                <div className="font-mono-num font-semibold text-accent">
                  {item.confidencePct.toFixed(1)}%
                </div>
              </div>

              <div className="bg-surface-sunken p-1 rounded border border-border-subtle">
                <div className="text-text-subtle text-[8px] uppercase tracking-wider">SUPPORT</div>
                <div className="font-mono-num font-semibold text-positive">
                  {item.supportAgents} agts
                </div>
              </div>

              <div className="bg-surface-sunken p-1 rounded border border-border-subtle">
                <div className="text-text-subtle text-[8px] uppercase tracking-wider">COUNTER</div>
                <div className="font-mono-num font-semibold text-text-muted">
                  {item.counterAgents} agts
                </div>
              </div>

              <div className="bg-surface-sunken p-1 rounded border border-border-subtle">
                <div className="text-text-subtle text-[8px] uppercase tracking-wider">RISK</div>
                <div className={`font-mono-num font-semibold rounded px-0.5 border ${getRiskBadge(item.riskImpact)}`}>
                  {item.riskImpact}
                </div>
              </div>
            </div>

            {/* Action Footer */}
            <div className="mt-2 flex items-center justify-between text-[10px] font-mono">
              <span className="text-text-subtle">RECOMMENDED ACTION:</span>
              <span className={`px-2 py-0.5 rounded border text-[10px] tracking-wide uppercase ${getActionBadge(item.action)}`}>
                {item.action}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Footer Info */}
      <div className="pt-2.5 mt-2 border-t border-border-subtle text-[10px] font-mono text-text-subtle flex items-center justify-between">
        <span>GATEWAY: QDRANT VECTOR MEMORY</span>
        <span className="text-positive flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-positive animate-pulse"></span>
          ACTIVE LISTENER
        </span>
      </div>
    </div>
  );
};
