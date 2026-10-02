import React from 'react';
import { MarketRegimeItem } from '../types';
import {   Activity } from 'lucide-react';

interface MarketRegimeFieldProps {
  instruments: MarketRegimeItem[];
  onSelectInstrument?: (item: MarketRegimeItem) => void;
  className?: string;
}

export const MarketRegimeField: React.FC<MarketRegimeFieldProps> = ({
  instruments,
  onSelectInstrument,
  className = '',
}) => {
  const getTrendColor = (trend: MarketRegimeItem['trend']) => {
    switch (trend) {
      case 'STRONG_BULL':
        return 'text-positive bg-positive-bg border-positive';
      case 'BULL':
        return 'text-positive bg-positive-bg border-positive';
      case 'SIDEWAYS':
        return 'text-text-muted bg-surface-veil border-border-strong';
      case 'BEAR':
        return 'text-destructive bg-destructive-bg border-destructive';
      case 'STRONG_BEAR':
        return 'text-destructive bg-destructive-bg border-destructive';
    }
  };

  // Micro SVG Sparkline — empty when the backend publishes no price series.
  const renderSparkline = (points: number[], isPositive: boolean) => {
    if (points.length < 2) {
      return <span className="text-[9px] font-mono text-text-subtle">NO PRICE FEED</span>;
    }
    const min = Math.min(...points);
    const max = Math.max(...points);
    const range = max - min || 1;
    const width = 64;
    const height = 18;

    const coords = points.map((p, i) => {
      const x = (i / (points.length - 1)) * width;
      const y = height - ((p - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    });

    const strokeColor = isPositive ? 'var(--color-positive)' : 'var(--color-destructive)';

    return (
      <svg width={width} height={height} className="overflow-visible">
        <polyline
          fill="none"
          stroke={strokeColor}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={coords.join(' ')}
        />
      </svg>
    );
  };

  return (
    <div className={`bg-[var(--color-surface-1)] border border-border-strong rounded-md p-3.5 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-text-strong uppercase">
            MARKET REGIME STATE FIELD
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-surface-veil text-text-muted border border-border-subtle">
            REAL-TIME FACTOR DISPERSION
          </span>
        </div>

        <div className="text-[10px] font-mono text-text-subtle">
          SOURCE: <span className="text-accent font-bold">/api/v1/regimes (LABELS ONLY)</span>
        </div>
      </div>

      {/* Grid of Market State Field Instruments */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-7 gap-2.5 py-2.5">
        {instruments.map((inst) => {
          const isPos = inst.change24hPct >= 0;
          return (
            <div
              key={inst.symbol}
              onClick={() => onSelectInstrument && onSelectInstrument(inst)}
              className="p-2.5 rounded bg-surface-veil hover:bg-surface-raised border border-border-subtle hover:border-accent transition-all cursor-pointer group flex flex-col justify-between shadow-sm"
            >
              {/* Row 1: Symbol & Price */}
              <div>
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="font-bold text-text-strong group-hover:text-accent transition-colors">
                    {inst.symbol}
                  </span>
                  <span className={`text-[10px] font-mono-num font-semibold ${isPos ? 'text-positive' : 'text-destructive'}`}>
                    {isPos ? '+' : ''}{inst.change24hPct.toFixed(2)}%
                  </span>
                </div>

                <div className="text-[11px] font-mono-num text-text mt-0.5">
                  {inst.price > 0
                    ? `$${inst.price >= 100 ? inst.price.toLocaleString(undefined, { minimumFractionDigits: 2 }) : inst.price.toFixed(2)}`
                    : <span className="text-text-subtle">— no price feed</span>}
                </div>
              </div>

              {/* Row 2: Sparkline & Trend */}
              <div className="my-2 flex items-center justify-between">
                <div className="shrink-0">
                  {renderSparkline(inst.sparkline, isPos)}
                </div>
                <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase ${getTrendColor(inst.trend)}`}>
                  {inst.trend.replace('_', ' ')}
                </span>
              </div>

              {/* Row 3: Regime & Confidence */}
              <div className="pt-1.5 border-t border-border-subtle text-[9px] font-mono space-y-1 text-text-muted">
                <div className="flex justify-between">
                  <span>REGIME:</span>
                  <span className="text-text-strong font-medium truncate max-w-[80px]" title={inst.regime}>
                    {inst.regime}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>VOL / CONF:</span>
                  <span className="text-accent font-mono-num">
                    {inst.volatility} ({inst.confidencePct}%)
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="pt-2 border-t border-border-subtle text-[10px] font-mono text-text-subtle flex items-center justify-between">
        <span>SOURCE: /api/v1/regimes</span>
        <span className="text-text-muted">{instruments.length} INSTRUMENTS LABELED</span>
      </div>
    </div>
  );
};
