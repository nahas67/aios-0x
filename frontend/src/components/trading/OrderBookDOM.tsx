import React from 'react';
import { Layers } from 'lucide-react';

interface OrderBookProps {
  symbol: string;
  markPrice: number;
  onSelectPrice?: (price: number) => void;
}

/**
 * L2 depth view. The backend exposes no Level-2 order-book feed, so this
 * renders a mounted honest empty state instead of simulated depth. The
 * mark strip still shows the last real mark passed in from the chart.
 */
export const OrderBookDOM: React.FC<OrderBookProps> = ({
  symbol,
  markPrice,
  onSelectPrice,
}) => {
  const precision = symbol.includes('JPY') || symbol.includes('7203') ? 1 : symbol.startsWith('PM-') ? 4 : 2;

  return (
    <div className="bg-[#08090d] border border-white/[0.08] rounded-xl flex flex-col overflow-hidden font-mono text-xs select-none">
      {/* Header */}
      <div className="bg-[#0b0d13] border-b border-white/[0.08] px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-bold text-slate-100 text-[11px] uppercase tracking-wider">L2 Order Book</span>
          <span className="text-[9px] px-1 py-0.2 rounded bg-white/[0.04] text-slate-400 border border-white/[0.06]">
            DOM
          </span>
        </div>

        <div className="flex items-center gap-2 text-[10px] text-slate-400">
          <span className="text-slate-400">Spread:</span>
          <span className="text-slate-500 font-bold font-mono-num">—</span>
        </div>
      </div>

      {/* Column Headers */}
      <div className="grid grid-cols-3 px-3 py-1.5 text-[9px] font-bold text-slate-400 border-b border-white/[0.04] uppercase">
        <div>Price (USD)</div>
        <div className="text-right">Size</div>
        <div className="text-right">Total</div>
      </div>

      {/* Honest absence: no L2 source exists server-side */}
      <div className="py-8 px-4 text-center">
        <div className="text-[11px] text-slate-300 font-semibold">No L2 feed configured</div>
        <div className="text-[10px] text-slate-500 mt-1 leading-relaxed">
          The backend publishes no Level-2 depth for {symbol}. Depth rows are withheld
          rather than simulated.
        </div>
      </div>

      {/* CURRENT MID / MARK PRICE STRIP */}
      <div className="my-0.5 px-3 py-1.5 bg-[#0e1017] border-y border-white/[0.06] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => onSelectPrice && markPrice > 0 && onSelectPrice(markPrice)}
            className="text-xs font-bold font-mono-num text-slate-100 hover:text-cyan-300 transition-colors"
            title="Use mark as limit price"
          >
            {markPrice > 0 ? markPrice.toFixed(precision) : "—"}
          </button>
          <span className="text-[9px] text-slate-400 uppercase">Mark</span>
        </div>

        <div className="flex items-center gap-1.5 text-[9px] text-slate-500">
          <span>source: chart feed</span>
        </div>
      </div>
    </div>
  );
};
