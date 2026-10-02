import React from 'react';
import { Activity } from 'lucide-react';

interface TradeTapeProps {
  symbol: string;
  markPrice: number;
}

/**
 * Time & sales tape. The backend publishes no per-trade tape feed, so this
 * renders a mounted honest empty state instead of simulated prints.
 */
export const TradeTapeTimeSales: React.FC<TradeTapeProps> = ({
  symbol,
}) => {
  return (
    <div className="bg-[var(--color-surface-0)] border border-border-strong rounded-xl flex flex-col overflow-hidden font-mono text-xs select-none">
      {/* Header */}
      <div className="bg-[var(--color-surface-2)] border-b border-border-strong px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-positive" />
          <span className="font-bold text-text-strong text-[11px] uppercase tracking-wider">Time & Sales Tape</span>
        </div>
        <span className="text-[9px] px-1.5 py-0.5 rounded bg-surface-veil text-text-subtle border border-border-subtle">
          NO FEED
        </span>
      </div>

      {/* Column Headers */}
      <div className="grid grid-cols-4 px-3 py-1.5 text-[9px] font-bold text-text-muted border-b border-border-subtle uppercase">
        <div>Time</div>
        <div className="text-right">Price</div>
        <div className="text-right">Size</div>
        <div className="text-right">Venue</div>
      </div>

      {/* Honest absence */}
      <div className="py-8 px-4 text-center">
        <div className="text-[11px] text-text font-semibold">No tape feed configured</div>
        <div className="text-[10px] text-text-subtle mt-1 leading-relaxed">
          The backend publishes no per-trade prints for {symbol}. Settled fills remain
          visible under Recent Executions.
        </div>
      </div>
    </div>
  );
};
