import React, { useState } from 'react';
import { 
   
   
   
   
  FlaskConical, 
  Activity, 
  CheckCircle2, 
  
  
  
  Play,
  
  
  Award,
  
  
  

} from 'lucide-react';

interface StrategyItem {
  id: string;
  name: string;
  family: string;
  targetSharpe: number;
  currentSharpe: number;
  maxDrawdownPct: number;
  capacityUsd: number;
  allocatedUsd: number;
  status: 'ACTIVE_PRODUCTION' | 'UNDER_REVIEW' | 'INCUBATION_SANDBOX' | 'PAPER_TESTING';
  winRatePct: number;
  tradesCount: number;
  description: string;
}

export const StrategyResearchWorkspace: React.FC = () => {
  const [strategies, setStrategies] = useState<StrategyItem[]>([
    {
      id: 'STRAT-01',
      name: 'Crypto Momentum & Funding Arbitrage',
      family: 'MOMENTUM_CARRY',
      targetSharpe: 3.12,
      currentSharpe: 2.94,
      maxDrawdownPct: 1.82,
      capacityUsd: 50000000,
      allocatedUsd: 28400000,
      status: 'ACTIVE_PRODUCTION',
      winRatePct: 68.4,
      tradesCount: 1420,
      description: 'Captures trend breakout momentum on spot while simultaneously harvesting positive funding yield on perpetual swap bases.',
    },
    {
      id: 'STRAT-02',
      name: 'Semiconductor Cross-Asset Dispersion',
      family: 'EQUITY_DISPERSION',
      targetSharpe: 2.65,
      currentSharpe: 2.81,
      maxDrawdownPct: 1.45,
      capacityUsd: 80000000,
      allocatedUsd: 42100000,
      status: 'ACTIVE_PRODUCTION',
      winRatePct: 62.9,
      tradesCount: 890,
      description: 'Exploits implied correlation divergence across high-beta semiconductor equities (NVDA, TSM, AMD) against broad index baskets.',
    },
    {
      id: 'STRAT-03',
      name: 'Macro Yield Curve Steepener',
      family: 'RATES_MACRO',
      targetSharpe: 2.10,
      currentSharpe: 2.24,
      maxDrawdownPct: 0.95,
      capacityUsd: 120000000,
      allocatedUsd: 35000000,
      status: 'ACTIVE_PRODUCTION',
      winRatePct: 71.2,
      tradesCount: 310,
      description: 'Positions for steepening of the US 2Y/10Y Treasury yield curve driven by Federal Reserve rate cut cycles.',
    },
    {
      id: 'STRAT-04',
      name: 'Volatility Regime Risk Harvesting',
      family: 'VOLATILITY_ARBITRAGE',
      targetSharpe: 2.40,
      currentSharpe: 2.05,
      maxDrawdownPct: 2.10,
      capacityUsd: 40000000,
      allocatedUsd: 15200000,
      status: 'UNDER_REVIEW',
      winRatePct: 59.1,
      tradesCount: 540,
      description: 'Extracts volatility risk premium by selectively underwriting out-of-the-money options during implied volatility spikes.',
    },
  ]);

  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('STRAT-01');

  // Backtest Simulation Controls
  const [splitRatio, setSplitRatio] = useState<string>('90d/30d');
  const [kellyFraction, setKellyFraction] = useState<number>(0.35);
  const [volTargetPct, setVolTargetPct] = useState<number>(14.0);
  const [stopLossPct, setStopLossPct] = useState<number>(2.5);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simulationResult, setSimulationResult] = useState<{
    sharpe: number;
    sortino: number;
    calmar: number;
    maxDd: number;
    winRate: number;
    profitFactor: number;
  } | null>(null);

  const [notification, setNotification] = useState<string | null>(null);

  const currentStrat = strategies.find(s => s.id === selectedStrategyId) || strategies[0];

  const handleRunBacktest = () => {
    setIsSimulating(true);
    setSimulationResult(null);

    setTimeout(() => {
      // Calculate realistic simulated metrics based on chosen parameters
      const baseSharpe = currentStrat.targetSharpe;
      const kellyBonus = (0.5 - Math.abs(0.35 - kellyFraction)) * 0.4;
      const simulatedSharpe = parseFloat((baseSharpe + kellyBonus + (Math.random() * 0.2 - 0.1)).toFixed(2));
      const simulatedMaxDd = parseFloat((currentStrat.maxDrawdownPct * (volTargetPct / 14.0) * (kellyFraction / 0.35)).toFixed(2));
      const simulatedWinRate = parseFloat((currentStrat.winRatePct + (Math.random() * 2 - 1)).toFixed(1));

      setSimulationResult({
        sharpe: simulatedSharpe,
        sortino: parseFloat((simulatedSharpe * 1.35).toFixed(2)),
        calmar: parseFloat((simulatedSharpe / Math.max(0.5, simulatedMaxDd) * 1.2).toFixed(2)),
        maxDd: simulatedMaxDd,
        winRate: simulatedWinRate,
        profitFactor: parseFloat((1.95 + (simulatedSharpe - 2.5) * 0.3).toFixed(2)),
      });

      setIsSimulating(false);
      setNotification(`Walk-forward backtest complete! Out-of-sample Sharpe: ${simulatedSharpe}`);
      setTimeout(() => setNotification(null), 4000);
    }, 1100);
  };

  const handlePromoteToProduction = (stratId: string) => {
    setStrategies(prev => prev.map(s => {
      if (s.id === stratId) {
        return { ...s, status: 'ACTIVE_PRODUCTION' };
      }
      return s;
    }));
    setNotification(`Strategy ${stratId} promoted to LIVE PRODUCTION with 0.35x Fractional Kelly allocation!`);
    setTimeout(() => setNotification(null), 4000);
  };

  // Sensitivity Matrix Data
  const sensitivityMatrix = [
    { kelly: '0.20x', sl: '1.5%', sharpe: 2.45, dd: 1.10 },
    { kelly: '0.20x', sl: '2.5%', sharpe: 2.70, dd: 1.25 },
    { kelly: '0.20x', sl: '3.5%', sharpe: 2.62, dd: 1.40 },
    { kelly: '0.35x', sl: '1.5%', sharpe: 2.82, dd: 1.55 },
    { kelly: '0.35x', sl: '2.5%', sharpe: 3.12, dd: 1.82 },
    { kelly: '0.35x', sl: '3.5%', sharpe: 2.95, dd: 2.10 },
    { kelly: '0.50x', sl: '1.5%', sharpe: 2.68, dd: 2.40 },
    { kelly: '0.50x', sl: '2.5%', sharpe: 2.85, dd: 2.75 },
    { kelly: '0.50x', sl: '3.5%', sharpe: 2.50, dd: 3.20 },
  ];

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              STRATEGY RESEARCH &amp; ALPHA LAB
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">
              FRAME 9 &amp; 10
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Walk-Forward Backtesting (90d/30d Split) • Purged K-Fold Cross-Validation • Fractional Kelly Budgeting
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">ACTIVE PRODUCTION ALPHAS:</span>{' '}
            <span className="text-white font-bold">{strategies.filter(s => s.status === 'ACTIVE_PRODUCTION').length}</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">WEIGHTED SHARPE:</span>{' '}
            <span className="text-emerald-400 font-bold">2.84</span>
          </div>
        </div>
      </div>

      {notification && (
        <div className="p-3 rounded bg-emerald-950/60 border border-emerald-500/60 text-emerald-300 text-xs flex items-center justify-between animate-fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>{notification}</span>
          </div>
        </div>
      )}

      {/* Strategies Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {strategies.map((strat) => {
          const isSelected = selectedStrategyId === strat.id;
          const isProd = strat.status === 'ACTIVE_PRODUCTION';

          return (
            <div
              key={strat.id}
              onClick={() => setSelectedStrategyId(strat.id)}
              className={`p-3.5 rounded-md cursor-pointer transition-all border ${
                isSelected
                  ? 'bg-cyan-950/40 border-cyan-500 shadow-[0_0_16px_rgba(0,240,255,0.2)]'
                  : 'bg-[#0d0f17] border-white/[0.08] hover:border-white/[0.2] hover:bg-white/[0.02]'
              }`}
            >
              <div className="flex items-center justify-between text-[10px] pb-2 border-b border-white/[0.06]">
                <span className="text-cyan-400 font-bold">{strat.id}</span>
                <span className={`px-1.5 py-0.2 rounded font-bold border ${
                  isProd ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-amber-950 text-amber-300 border-amber-800'
                }`}>
                  {strat.status}
                </span>
              </div>

              <div className="mt-2">
                <div className="font-bold text-white text-xs leading-snug line-clamp-1">{strat.name}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{strat.family}</div>
              </div>

              <div className="grid grid-cols-2 gap-2 mt-3 pt-2 border-t border-white/[0.04] text-[11px]">
                <div>
                  <span className="text-[9px] text-slate-500 block">SHARPE</span>
                  <span className="text-emerald-400 font-bold font-mono">{strat.currentSharpe.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-[9px] text-slate-500 block">MAX DD</span>
                  <span className="text-slate-300 font-mono">{strat.maxDrawdownPct}%</span>
                </div>
                <div>
                  <span className="text-[9px] text-slate-500 block">CAPACITY</span>
                  <span className="text-white font-mono">${(strat.capacityUsd / 1000000).toFixed(0)}M</span>
                </div>
                <div>
                  <span className="text-[9px] text-slate-500 block">WIN RATE</span>
                  <span className="text-cyan-300 font-mono">{strat.winRatePct}%</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Interactive Backtester & Sandbox Studio */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-4">
        <div className="flex flex-wrap items-center justify-between pb-3 border-b border-white/[0.06] gap-2">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase text-white tracking-wider">
              WALK-FORWARD BACKTESTER &amp; PARAMETER SENSITIVITY STUDIO — {currentStrat.name}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            {currentStrat.status !== 'ACTIVE_PRODUCTION' && (
              <button
                onClick={() => handlePromoteToProduction(currentStrat.id)}
                className="px-3 py-1 rounded bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-xs flex items-center gap-1 shadow-[0_0_12px_rgba(16,185,129,0.3)]"
              >
                <Award className="w-3.5 h-3.5" />
                <span>PROMOTE TO PRODUCTION</span>
              </button>
            )}
          </div>
        </div>

        {/* Strategy Synopsis */}
        <p className="text-xs text-slate-300 bg-black/40 p-3 rounded border border-white/[0.06] leading-relaxed">
          {currentStrat.description}
        </p>

        {/* Interactive Parameter Controls */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
          <div className="p-3 rounded bg-white/[0.02] border border-white/[0.06] space-y-1.5">
            <label className="text-[10px] text-slate-400 uppercase tracking-wider block">
              Walk-Forward Split
            </label>
            <select
              value={splitRatio}
              onChange={(e) => setSplitRatio(e.target.value)}
              className="w-full bg-black/60 border border-white/[0.1] rounded px-2 py-1.5 text-white font-mono"
            >
              <option value="60d/20d">60d In-Sample / 20d Out-of-Sample</option>
              <option value="90d/30d">90d In-Sample / 30d Out-of-Sample (Standard)</option>
              <option value="180d/60d">180d In-Sample / 60d Out-of-Sample (Macro)</option>
            </select>
          </div>

          <div className="p-3 rounded bg-white/[0.02] border border-white/[0.06] space-y-1.5">
            <div className="flex justify-between text-[10px]">
              <span className="text-slate-400 uppercase tracking-wider">Kelly Sizing Fraction</span>
              <span className="text-cyan-300 font-mono font-bold">{kellyFraction.toFixed(2)}x</span>
            </div>
            <input
              type="range"
              min="0.10"
              max="0.60"
              step="0.05"
              value={kellyFraction}
              onChange={(e) => setKellyFraction(parseFloat(e.target.value))}
              className="w-full accent-cyan-400 cursor-pointer"
            />
            <div className="flex justify-between text-[9px] text-slate-500">
              <span>0.10x (Conservative)</span>
              <span>0.60x (Aggressive)</span>
            </div>
          </div>

          <div className="p-3 rounded bg-white/[0.02] border border-white/[0.06] space-y-1.5">
            <div className="flex justify-between text-[10px]">
              <span className="text-slate-400 uppercase tracking-wider">Volatility Target</span>
              <span className="text-cyan-300 font-mono font-bold">{volTargetPct.toFixed(1)}%</span>
            </div>
            <input
              type="range"
              min="8.0"
              max="24.0"
              step="1.0"
              value={volTargetPct}
              onChange={(e) => setVolTargetPct(parseFloat(e.target.value))}
              className="w-full accent-cyan-400 cursor-pointer"
            />
            <div className="flex justify-between text-[9px] text-slate-500">
              <span>8% (Low Vol)</span>
              <span>24% (High Beta)</span>
            </div>
          </div>

          <div className="p-3 rounded bg-white/[0.02] border border-white/[0.06] space-y-1.5 flex flex-col justify-between">
            <div>
              <div className="flex justify-between text-[10px]">
                <span className="text-slate-400 uppercase tracking-wider">Stop Loss Threshold</span>
                <span className="text-rose-400 font-mono font-bold">{stopLossPct.toFixed(1)}%</span>
              </div>
              <input
                type="range"
                min="1.0"
                max="5.0"
                step="0.5"
                value={stopLossPct}
                onChange={(e) => setStopLossPct(parseFloat(e.target.value))}
                className="w-full accent-rose-400 cursor-pointer"
              />
            </div>

            <button
              onClick={handleRunBacktest}
              disabled={isSimulating}
              className={`w-full py-1.5 rounded font-bold text-xs flex items-center justify-center gap-1.5 transition-all ${
                isSimulating
                  ? 'bg-cyan-950 text-cyan-400 border border-cyan-800 animate-pulse'
                  : 'bg-cyan-500 hover:bg-cyan-400 text-black shadow-[0_0_12px_rgba(0,240,255,0.3)]'
              }`}
            >
              {isSimulating ? (
                <>
                  <FlaskConical className="w-3.5 h-3.5 animate-spin" />
                  <span>SIMULATING 1,000 BARS...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  <span>RUN WALK-FORWARD BACKTEST</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Backtest Results Cards */}
        {simulationResult && (
          <div className="p-4 rounded bg-cyan-950/30 border border-cyan-500/40 space-y-3 animate-fade-in">
            <div className="flex items-center justify-between pb-2 border-b border-cyan-500/20">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-cyan-400" />
                <span className="font-bold text-xs text-white uppercase tracking-wider">
                  OUT-OF-SAMPLE WALK-FORWARD SIMULATION METRICS
                </span>
              </div>
              <span className="text-[10px] text-cyan-300 font-mono">1,000 Walk-Forward Iterations</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.08]">
                <span className="text-[9px] text-slate-400 block">SHARPE RATIO</span>
                <span className="text-lg font-bold text-emerald-400 font-mono">{simulationResult.sharpe}</span>
              </div>
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.08]">
                <span className="text-[9px] text-slate-400 block">SORTINO RATIO</span>
                <span className="text-lg font-bold text-cyan-300 font-mono">{simulationResult.sortino}</span>
              </div>
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.08]">
                <span className="text-[9px] text-slate-400 block">CALMAR RATIO</span>
                <span className="text-lg font-bold text-indigo-300 font-mono">{simulationResult.calmar}</span>
              </div>
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.08]">
                <span className="text-[9px] text-slate-400 block">MAX DRAWDOWN</span>
                <span className="text-lg font-bold text-rose-400 font-mono">{simulationResult.maxDd}%</span>
              </div>
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.08]">
                <span className="text-[9px] text-slate-400 block">WIN RATE</span>
                <span className="text-lg font-bold text-white font-mono">{simulationResult.winRate}%</span>
              </div>
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.08]">
                <span className="text-[9px] text-slate-400 block">PROFIT FACTOR</span>
                <span className="text-lg font-bold text-emerald-300 font-mono">{simulationResult.profitFactor}</span>
              </div>
            </div>
          </div>
        )}

        {/* Parameter Sensitivity Heatmap */}
        <div className="pt-2">
          <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-2 font-bold">
            PARAMETER SENSITIVITY GRID (KELLY FRACTION VS STOP-LOSS THRESHOLD)
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            {sensitivityMatrix.map((item, idx) => {
              const isBest = item.sharpe >= 3.0;
              return (
                <div
                  key={idx}
                  className={`p-2.5 rounded border text-xs flex justify-between items-center ${
                    isBest
                      ? 'bg-emerald-950/60 border-emerald-500 text-emerald-300 shadow-[0_0_10px_rgba(16,185,129,0.2)]'
                      : 'bg-black/30 border-white/[0.06] text-slate-300'
                  }`}
                >
                  <div>
                    <div className="text-[9px] text-slate-400">Kelly {item.kelly} • SL {item.sl}</div>
                    <div className="font-bold mt-0.5">Sharpe: {item.sharpe.toFixed(2)}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[9px] text-slate-400">Max DD</div>
                    <div className="text-rose-400 font-mono text-[11px]">{item.dd.toFixed(2)}%</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
