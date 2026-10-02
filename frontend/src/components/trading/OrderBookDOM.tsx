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
    <div className="bg-[var(--color-surface-0)] border border-border-strong rounded-xl flex flex-col overflow-hidden font-mono text-xs select-none">
      {/* Header */}
      <div className="bg-[var(--color-surface-2)] border-b border-border-strong px-3 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-accent" />
          <span className="font-bold text-text-strong text-[11px] uppercase tracking-wider">L2 Order Book</span>
          <span className="text-[9px] px-1 py-0.2 rounded bg-surface-veil text-text-muted border border-border-subtle">
            DOM
          </span>
        </div>

        <div className="flex items-center gap-2 text-[10px] text-text-muted">
          <span className="text-text-muted">Spread:</span>
          <span className="text-text-subtle font-bold font-mono-num">—</span>
        </div>
      </div>

      {/* Column Headers */}
      <div className="grid grid-cols-3 px-3 py-1.5 text-[9px] font-bold text-text-muted border-b border-border-subtle uppercase">
        <div>Price (USD)</div>
        <div className="text-right">Size</div>
        <div className="text-right">Total</div>
      </div>

      {/* Honest absence: no L2 source exists server-side */}
      <div className="py-8 px-4 text-center">
        <div className="text-[11px] text-text font-semibold">No L2 feed configured</div>
        <div className="text-[10px] text-text-subtle mt-1 leading-relaxed">
          The backend publishes no Level-2 depth for {symbol}. Depth rows are withheld
          rather than simulated.
        </div>
      </div>

      {/* CURRENT MID / MARK PRICE STRIP */}
      <div className="my-0.5 px-3 py-1.5 bg-[var(--color-surface-1)] border-y border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => onSelectPrice && markPrice > 0 && onSelectPrice(markPrice)}
            className="text-xs font-bold font-mono-num text-text-strong hover:text-accent transition-colors"
            title="Use mark as limit price"
          >
            {markPrice > 0 ? markPrice.toFixed(precision) : "—"}
          </button>
          <span className="text-[9px] text-text-muted uppercase">Mark</span>
        </div>

        <div className="flex items-center gap-1.5 text-[9px] text-text-subtle">
          <span>source: chart feed</span>
        </div>
      </div>
    </div>
  );
};
