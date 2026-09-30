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
        return 'text-emerald-400 bg-emerald-950/60 border-emerald-700/60';
      case 'BULL':
        return 'text-emerald-300 bg-emerald-950/40 border-emerald-800/40';
      case 'SIDEWAYS':
        return 'text-slate-400 bg-white/[0.04] border-white/[0.08]';
      case 'BEAR':
        return 'text-rose-300 bg-rose-950/40 border-rose-800/40';
      case 'STRONG_BEAR':
        return 'text-rose-400 bg-rose-950/60 border-rose-700/60';
    }
  };

  // Micro SVG Sparkline
  const renderSparkline = (points: number[], isPositive: boolean) => {
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

    const strokeColor = isPositive ? '#10b981' : '#f43f5e';

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
    <div className={`bg-[#0d0f17] border border-white/[0.08] rounded-md p-3.5 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-slate-100 uppercase">
            MARKET REGIME STATE FIELD
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-400 border border-white/[0.06]">
            REAL-TIME FACTOR DISPERSION
          </span>
        </div>

        <div className="text-[10px] font-mono text-slate-500">
          GLOBAL REGIME: <span className="text-cyan-300 font-bold">EXPANSIONARY MOMENTUM</span>
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
              className="p-2.5 rounded bg-white/[0.02] hover:bg-white/[0.05] border border-white/[0.06] hover:border-cyan-500/40 transition-all cursor-pointer group flex flex-col justify-between shadow-sm"
            >
              {/* Row 1: Symbol & Price */}
              <div>
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="font-bold text-white group-hover:text-cyan-300 transition-colors">
                    {inst.symbol}
                  </span>
                  <span className={`text-[10px] font-mono-num font-semibold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {isPos ? '+' : ''}{inst.change24hPct.toFixed(2)}%
                  </span>
                </div>

                <div className="text-[11px] font-mono-num text-slate-300 mt-0.5">
                  ${inst.price >= 100 ? inst.price.toLocaleString(undefined, { minimumFractionDigits: 2 }) : inst.price.toFixed(2)}
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
              <div className="pt-1.5 border-t border-white/[0.04] text-[9px] font-mono space-y-1 text-slate-400">
                <div className="flex justify-between">
                  <span>REGIME:</span>
                  <span className="text-slate-200 font-medium truncate max-w-[80px]" title={inst.regime}>
                    {inst.regime}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>VOL / CONF:</span>
                  <span className="text-cyan-300 font-mono-num">
                    {inst.volatility} ({inst.confidencePct}%)
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="pt-2 border-t border-white/[0.06] text-[10px] font-mono text-slate-500 flex items-center justify-between">
        <span>TIMESCALEDB CONTINUOUS DOWNSAMPLING (5m → 1h → 1d)</span>
        <span className="text-slate-400">7/7 INSTRUMENTS SYNCHRONIZED</span>
      </div>
    </div>
  );
};
