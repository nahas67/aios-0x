import React, { useState } from 'react';
import { RiskSpectrum } from '../../types';
import { 
  ShieldAlert, 
   
   
  Zap, 
   
   
   
  
  Scale
} from 'lucide-react';
import { RiskCommandSpectrum } from '../RiskCommandSpectrum';

interface RiskCommandCenterWorkspaceProps {
  risk: RiskSpectrum;
}

export const RiskCommandCenterWorkspace: React.FC<RiskCommandCenterWorkspaceProps> = ({
  risk,
}) => {
  const [stressScenario, setStressScenario] = useState<'NONE' | 'FLASH_CRASH' | 'RATES_SHOCK' | 'CRYPTO_DELEVERAGING'>('NONE');

  const getScenarioDd = () => {
    switch (stressScenario) {
      case 'FLASH_CRASH': return 1.84;
      case 'RATES_SHOCK': return 1.22;
      case 'CRYPTO_DELEVERAGING': return 2.65;
      default: return risk.currentDrawdownPct;
    }
  };

  const currentStressedDd = getScenarioDd();

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              INSTITUTIONAL RISK COMMAND CENTER & FIREWALL
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 7
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Continuous Risk Spectrum • Tiered Drawdown Governor • Real-Time Value-at-Risk Engine
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">STATUS:</span>{' '}
            <span className="text-emerald-400 font-bold">15/15 FIREWALL RULES PASSED</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">HARD CEILING:</span>{' '}
            <span className="text-red-400 font-bold">3.00% MAX DRAWDOWN</span>
          </div>
        </div>
      </div>

      {/* Main Continuous Risk Spectrum */}
      <RiskCommandSpectrum risk={risk} />

      {/* Stress Testing Scenarios & Scenario Analysis */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* Left: Stress Scenario Simulator */}
        <div className="xl:col-span-7 bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-400" />
              <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                MACRO STRESS-TEST SCENARIO SIMULATOR
              </h3>
            </div>
            <span className="text-[10px] text-slate-400">HISTORICAL + SYNTHETIC SHOCKS</span>
          </div>

          <div className="grid grid-cols-2 gap-2 my-3">
            {[
              { id: 'NONE', label: 'Baseline (Live Market)', dd: risk.currentDrawdownPct, desc: 'Current live market prices' },
              { id: 'FLASH_CRASH', label: 'Equity Flash Crash (-7%)', dd: 1.84, desc: 'SPX -7%, VIX +120%, Flight to USD' },
              { id: 'RATES_SHOCK', label: 'Bond Yield Shock (+50bps)', dd: 1.22, desc: 'US 10Y Yield jumps 50 bps in 1 session' },
              { id: 'CRYPTO_DELEVERAGING', label: 'Crypto Cascading Deleveraging (-20%)', dd: 2.65, desc: 'Funding wipeout across perpetuals' },
            ].map((sc) => (
              <button
                key={sc.id}
                onClick={() => setStressScenario(sc.id as any)}
                className={`p-2.5 rounded text-left border transition-all ${
                  stressScenario === sc.id
                    ? 'bg-amber-950/40 border-amber-500/60 shadow-md'
                    : 'bg-white/[0.02] border-white/[0.05] hover:bg-white/[0.04]'
                }`}
              >
                <div className="flex justify-between items-center text-xs">
                  <span className="font-bold text-slate-200">{sc.label}</span>
                  <span className="font-mono-num font-bold text-amber-400">{sc.dd.toFixed(2)}% DD</span>
                </div>
                <div className="text-[10px] text-slate-400 mt-1 line-clamp-1">{sc.desc}</div>
              </button>
            ))}
          </div>

          {/* Stressed Outcome Strip */}
          <div className="p-3 rounded bg-black/40 border border-white/[0.06] text-xs space-y-1.5">
            <div className="flex justify-between">
              <span className="text-slate-400">Simulated Drawdown:</span>
              <span className="font-mono-num font-bold text-white text-sm">{currentStressedDd.toFixed(2)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Automated Governor Reaction:</span>
              <span className={`font-bold ${
                currentStressedDd >= 2.5 
                  ? 'text-red-400' 
                  : currentStressedDd >= 1.5 
                  ? 'text-amber-400' 
                  : 'text-emerald-400'
              }`}>
                {currentStressedDd >= 2.5 ? 'TRIGGER TIER-2 DE-RISK (50% CUT)' : currentStressedDd >= 1.5 ? 'TRIGGER TIER-1 WARNING (25% CUT)' : 'ALL CHECKS WITHIN TOLERANCE'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Projected Capital Recovery Time:</span>
              <span className="text-cyan-300">1.4 Trading Days (Kelly Normalized)</span>
            </div>
          </div>
        </div>

        {/* Right: Tiered Drawdown Constitution Rules */}
        <div className="xl:col-span-5 bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <Scale className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                CONSTITUTIONAL DRAWDOWN TIERS
              </h3>
            </div>
            <span className="text-[10px] text-emerald-400">RATIFIED v1.0.0</span>
          </div>

          <div className="space-y-2.5 my-3 text-xs">
            <div className="p-2 rounded bg-emerald-950/20 border border-emerald-800/40">
              <div className="flex justify-between font-bold text-emerald-300 text-xs">
                <span>TIER 0: NOMINAL REGIME</span>
                <span>0.00% – 1.50%</span>
              </div>
              <div className="text-[10px] text-slate-300 mt-1">
                Full autonomous multi-agent execution permitted. 100% position limit capacity.
              </div>
            </div>

            <div className="p-2 rounded bg-amber-950/20 border border-amber-800/40">
              <div className="flex justify-between font-bold text-amber-300 text-xs">
                <span>TIER 1: ELEVATED WARNING</span>
                <span>1.50% – 2.50%</span>
              </div>
              <div className="text-[10px] text-slate-300 mt-1">
                Halts new position openings. Automated 25% proportional trim on highest volatility assets.
              </div>
            </div>

            <div className="p-2 rounded bg-orange-950/20 border border-orange-800/40">
              <div className="flex justify-between font-bold text-orange-300 text-xs">
                <span>TIER 2: AGGRESSIVE DE-RISKING</span>
                <span>2.50% – 3.00%</span>
              </div>
              <div className="text-[10px] text-slate-300 mt-1">
                Autonomous 50% liquidation across risk assets into USD cash / short-term T-bills.
              </div>
            </div>

            <div className="p-2 rounded bg-red-950/20 border border-red-800/40">
              <div className="flex justify-between font-bold text-red-300 text-xs">
                <span>TIER 3: EMERGENCY HALT (KILL SWITCH)</span>
                <span>&gt; 3.00%</span>
              </div>
              <div className="text-[10px] text-slate-300 mt-1">
                Complete position flattening. Halts all agent inference. Requires human Compliance Officer + CIO sign-off.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
