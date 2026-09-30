import React from 'react';
import { MarketRegimeItem } from '../../types';
import { 
   
  Activity, 
  Globe, 
   
  Calendar, 
  Layers, 
   
  

} from 'lucide-react';
import { MarketRegimeField } from '../MarketRegimeField';

interface MarketIntelligenceWorkspaceProps {
  instruments: MarketRegimeItem[];
}

export const MarketIntelligenceWorkspace: React.FC<MarketIntelligenceWorkspaceProps> = ({
  instruments,
}) => {
  // Cross-Asset Correlation Matrix
  const correlationAssets = ['BTC', 'ETH', 'SPX', 'NVDA', 'GOLD', 'DXY'];
  const correlationMatrix = [
    [1.00, 0.84, 0.38, 0.44, 0.12, -0.42], // BTC
    [0.84, 1.00, 0.41, 0.49, 0.08, -0.38], // ETH
    [0.38, 0.41, 1.00, 0.78, -0.05, -0.62], // SPX
    [0.44, 0.49, 0.78, 1.00, -0.11, -0.55], // NVDA
    [0.12, 0.08, -0.05, -0.11, 1.00, -0.31], // GOLD
    [-0.42, -0.38, -0.62, -0.55, -0.31, 1.00], // DXY
  ];

  const getHeatmapColor = (val: number) => {
    if (val === 1) return 'bg-cyan-600/40 text-cyan-200';
    if (val > 0.6) return 'bg-emerald-950/80 text-emerald-300';
    if (val > 0.2) return 'bg-emerald-950/40 text-emerald-400';
    if (val >= -0.2) return 'bg-white/[0.04] text-slate-400';
    if (val >= -0.6) return 'bg-rose-950/40 text-rose-400';
    return 'bg-rose-950/80 text-rose-300';
  };

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              CROSS-ASSET MARKET REGIME & FACTOR FIELD
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 3
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            TimescaleDB Continuous Aggregates • Realized vs Implied Dispersion • Macro Velocity
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1 rounded">
            <span className="text-slate-400">FED POLICY PRICING:</span>{' '}
            <span className="text-cyan-300 font-bold">25 BPS CUT (88%)</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1 rounded">
            <span className="text-slate-400">GLOBAL LIQUIDITY:</span>{' '}
            <span className="text-emerald-400 font-bold">EXPANDING (+2.4% MoM)</span>
          </div>
        </div>
      </div>

      {/* State Field */}
      <MarketRegimeField instruments={instruments} />

      {/* Grid: Correlation Heatmap + Volatility Surface & Term Structure */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* Correlation Heatmap */}
        <div className="xl:col-span-7 bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                ROLLING 60-DAY CORRELATION MATRIX
              </h3>
            </div>
            <span className="text-[10px] text-slate-400">COVARIANCE RESCALED</span>
          </div>

          <div className="overflow-x-auto py-3">
            <table className="w-full text-center text-xs border-collapse">
              <thead>
                <tr>
                  <th className="p-2 text-slate-500 text-left">ASSET</th>
                  {correlationAssets.map(a => (
                    <th key={a} className="p-2 text-slate-300 font-bold">{a}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {correlationAssets.map((rowAsset, rIdx) => (
                  <tr key={rowAsset} className="border-t border-white/[0.04]">
                    <td className="p-2 font-bold text-slate-300 text-left">{rowAsset}</td>
                    {correlationMatrix[rIdx].map((val, cIdx) => (
                      <td key={cIdx} className="p-1">
                        <div className={`py-1.5 px-2 rounded font-mono-num font-semibold text-xs ${getHeatmapColor(val)}`}>
                          {val >= 0 ? '+' : ''}{val.toFixed(2)}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pt-2 border-t border-white/[0.06] flex items-center justify-between text-[10px] text-slate-500">
            <span>DXY Anti-correlation coefficient: <strong className="text-rose-400">-0.62 to equities</strong></span>
            <span>Regime stability index: <strong className="text-emerald-400">HIGH (0.89)</strong></span>
          </div>
        </div>

        {/* Volatility Surface & Macro Calendar */}
        <div className="xl:col-span-5 space-y-4">
          {/* Volatility Structure */}
          <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                  VOLATILITY TERM STRUCTURE
                </h3>
              </div>
              <span className="text-[10px] text-cyan-300">CONTANGO</span>
            </div>

            <div className="space-y-2.5 py-3 text-xs">
              <div>
                <div className="flex justify-between text-slate-400 text-[11px] mb-1">
                  <span>BTC 30D IV vs RV</span>
                  <span className="text-cyan-300 font-mono-num font-bold">52.4% IV / 44.1% RV (+8.3% Premium)</span>
                </div>
                <div className="h-1.5 bg-black/40 rounded-full overflow-hidden flex">
                  <div className="h-full bg-cyan-400 w-[60%]"></div>
                  <div className="h-full bg-indigo-500 w-[20%]"></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between text-slate-400 text-[11px] mb-1">
                  <span>VIX INDEX (EQUITY VOL)</span>
                  <span className="text-emerald-400 font-mono-num font-bold">14.82 (-0.64) • SUBDUED</span>
                </div>
                <div className="h-1.5 bg-black/40 rounded-full overflow-hidden flex">
                  <div className="h-full bg-emerald-400 w-[30%]"></div>
                </div>
              </div>

              <div>
                <div className="flex justify-between text-slate-400 text-[11px] mb-1">
                  <span>MOVE INDEX (BOND VOL)</span>
                  <span className="text-amber-400 font-mono-num font-bold">96.5 (+2.1) • ELEVATED</span>
                </div>
                <div className="h-1.5 bg-black/40 rounded-full overflow-hidden flex">
                  <div className="h-full bg-amber-400 w-[55%]"></div>
                </div>
              </div>
            </div>
          </div>

          {/* Macro Catalysts Feed */}
          <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                  MACRO EVENT PROBABILITY HORIZON
                </h3>
              </div>
              <span className="text-[10px] text-slate-400">NEXT 7 DAYS</span>
            </div>

            <div className="space-y-2 py-2 text-xs">
              <div className="p-2 rounded bg-white/[0.02] border border-white/[0.05] flex items-center justify-between">
                <div>
                  <div className="font-bold text-slate-200">US CORE CPI RELEASE</div>
                  <div className="text-[10px] text-slate-400">Consensus: 0.2% MoM • Agent impact: Volatility Spike</div>
                </div>
                <span className="text-[10px] font-bold text-amber-400 px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800">
                  IN 14 HOURS
                </span>
              </div>

              <div className="p-2 rounded bg-white/[0.02] border border-white/[0.05] flex items-center justify-between">
                <div>
                  <div className="font-bold text-slate-200">FOMC INTEREST RATE DECISION</div>
                  <div className="text-[10px] text-slate-400">Probability: 25 bps Cut (88.4%)</div>
                </div>
                <span className="text-[10px] font-bold text-cyan-400 px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-800">
                  IN 3 DAYS
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
