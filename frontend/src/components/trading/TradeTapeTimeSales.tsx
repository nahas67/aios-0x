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
    <div className="bg-[#08090d] border border-white/[0.08] rounded-xl flex flex-col overflow-hidden font-mono text-xs select-none">
      {/* Header */}
      <div className="bg-[#0b0d13] border-b border-white/[0.08] px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-emerald-400" />
          <span className="font-bold text-slate-100 text-[11px] uppercase tracking-wider">Time & Sales Tape</span>
        </div>
        <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-500 border border-white/[0.06]">
          NO FEED
        </span>
      </div>

      {/* Column Headers */}
      <div className="grid grid-cols-4 px-3 py-1.5 text-[9px] font-bold text-slate-400 border-b border-white/[0.04] uppercase">
        <div>Time</div>
        <div className="text-right">Price</div>
        <div className="text-right">Size</div>
        <div className="text-right">Venue</div>
      </div>

      {/* Honest absence */}
      <div className="py-8 px-4 text-center">
        <div className="text-[11px] text-slate-300 font-semibold">No tape feed configured</div>
        <div className="text-[10px] text-slate-500 mt-1 leading-relaxed">
          The backend publishes no per-trade prints for {symbol}. Settled fills remain
          visible under Recent Executions.
        </div>
      </div>
    </div>
  );
};
