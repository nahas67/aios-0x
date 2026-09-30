import React, { useState } from 'react';
import { RiskSpectrum } from '../types';
import { ShieldAlert,      Zap } from 'lucide-react';

interface RiskCommandSpectrumProps {
  risk: RiskSpectrum;
  onOpenRiskDrawer?: () => void;
  className?: string;
}

export const RiskCommandSpectrum: React.FC<RiskCommandSpectrumProps> = ({
  risk,
  onOpenRiskDrawer,
  className = '',
}) => {
  const [stressDelta, setStressDelta] = useState<number>(0);

  // Compute stressed values if simulator slider is engaged
  const effectiveDd = Math.max(0, risk.currentDrawdownPct + stressDelta);

  const getStatusLevel = (dd: number) => {
    if (dd >= risk.emergencyHaltPct) return { text: 'EMERGENCY HALT (KILL SWITCH)', color: 'text-red-400 bg-red-950/80 border-red-700' };
    if (dd >= risk.reductionThresholdPct) return { text: 'TIER-2 REDUCTION (50% CUT)', color: 'text-amber-400 bg-amber-950/80 border-amber-600' };
    if (dd >= risk.warningThresholdPct) return { text: 'TIER-1 WARNING (25% CUT)', color: 'text-amber-300 bg-amber-950/50 border-amber-800' };
    return { text: 'CONSTITUTIONALLY NOMINAL', color: 'text-emerald-400 bg-emerald-950/40 border-emerald-800' };
  };

  const status = getStatusLevel(effectiveDd);

  // Scaled percentage along 0% to 3.5% spectrum bar
  const maxScale = 3.5;
  const currentPosPct = Math.min(100, (effectiveDd / maxScale) * 100);
  const warningPosPct = (risk.warningThresholdPct / maxScale) * 100;
  const reductionPosPct = (risk.reductionThresholdPct / maxScale) * 100;
  const haltPosPct = (risk.emergencyHaltPct / maxScale) * 100;

  return (
    <div className={`bg-[#0d0f17] border border-white/[0.08] rounded-md p-3.5 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-slate-100 uppercase">
            PORTFOLIO RISK COMMAND
          </h3>
          <span className={`text-[9px] font-mono px-2 py-0.5 rounded border font-semibold ${status.color}`}>
            {status.text}
          </span>
        </div>

        {onOpenRiskDrawer && (
          <button
            onClick={onOpenRiskDrawer}
            className="text-[11px] font-mono text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
          >
            <span>INSPECT FIREWALL</span>
            <span>→</span>
          </button>
        )}
      </div>

      {/* The Continuous Risk Spectrum Bar */}
      <div className="py-3">
        <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 pb-1.5">
          <span className="flex items-center gap-1">
            <span className="text-slate-500">OPERATIONAL STATE:</span>
            <span className="text-white font-mono-num font-bold text-xs">{effectiveDd.toFixed(2)}% DD</span>
          </span>
          <span className="text-slate-500">
            BUFFER TO HALT: <span className="text-cyan-300 font-mono-num font-bold">{(risk.emergencyHaltPct - effectiveDd).toFixed(2)}%</span>
          </span>
        </div>

        {/* Continuous Spectrum Track */}
        <div className="relative h-6 w-full rounded bg-black/60 border border-white/[0.08] overflow-hidden p-0.5 flex">
          {/* Zone 1: Nominal (Green) */}
          <div 
            style={{ width: `${warningPosPct}%` }}
            className="h-full bg-gradient-to-r from-emerald-950/60 to-emerald-900/40 border-r border-emerald-500/30 flex items-center justify-start pl-2"
          >
            <span className="text-[9px] font-mono text-emerald-400/70 uppercase">NOMINAL</span>
          </div>

          {/* Zone 2: Warning (Yellow/Amber) */}
          <div 
            style={{ width: `${reductionPosPct - warningPosPct}%` }}
            className="h-full bg-gradient-to-r from-amber-950/50 to-amber-900/50 border-r border-amber-500/40 flex items-center justify-center"
          >
            <span className="text-[9px] font-mono text-amber-300/70 uppercase">WARN</span>
          </div>

          {/* Zone 3: Reduction (Orange/Red) */}
          <div 
            style={{ width: `${haltPosPct - reductionPosPct}%` }}
            className="h-full bg-gradient-to-r from-orange-950/60 to-red-950/60 border-r border-red-500/50 flex items-center justify-center"
          >
            <span className="text-[9px] font-mono text-orange-300/70 uppercase">REDUCE</span>
          </div>

          {/* Zone 4: Emergency Halt (Dark Red) */}
          <div 
            className="flex-1 h-full bg-red-950/80 flex items-center justify-center"
          >
            <span className="text-[9px] font-mono text-red-400 font-bold uppercase tracking-tighter">HALT</span>
          </div>

          {/* Active Current Position Needle Pin */}
          <div 
            className="absolute top-0 bottom-0 w-1 bg-white shadow-[0_0_10px_#ffffff] z-10 transition-all duration-150"
            style={{ left: `${currentPosPct}%` }}
          >
            <div className="absolute -top-1 -left-1.5 w-4 h-2 bg-white rounded-full shadow-md" />
            <div className="absolute -bottom-1 -left-1.5 w-4 h-2 bg-white rounded-full shadow-md" />
          </div>
        </div>

        {/* Milestone Threshold Labels below bar */}
        <div className="relative w-full h-4 mt-1 text-[10px] font-mono text-slate-500">
          <span className="absolute left-0">0.0%</span>
          <span 
            className="absolute -translate-x-1/2 text-amber-400"
            style={{ left: `${warningPosPct}%` }}
          >
            1.50% Warn
          </span>
          <span 
            className="absolute -translate-x-1/2 text-orange-400"
            style={{ left: `${reductionPosPct}%` }}
          >
            2.50% Reduce
          </span>
          <span 
            className="absolute -translate-x-1/2 text-red-400 font-semibold"
            style={{ left: `${haltPosPct}%` }}
          >
            3.00% Halt
          </span>
        </div>
      </div>

      {/* Operational Limits Matrix: Position Concentration, Class Exposure, Correlation */}
      <div className="grid grid-cols-3 gap-2.5 pt-2 border-t border-white/[0.06]">
        {/* Concentration */}
        <div className="p-2 rounded bg-white/[0.02] border border-white/[0.05]">
          <div className="flex justify-between text-[10px] font-mono text-slate-400">
            <span>MAX POSITION CONCENTRATION</span>
            <span className="text-slate-500">LIMIT: {risk.maxPositionConcentrationPct}%</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-sm font-mono-num font-bold text-white">
              {risk.positionConcentrationPct.toFixed(1)}%
            </span>
            <span className="text-[10px] font-mono text-emerald-400">PASSED</span>
          </div>
          <div className="w-full h-1 bg-black/40 rounded-full mt-1 overflow-hidden">
            <div 
              className="h-full bg-cyan-400 rounded-full"
              style={{ width: `${(risk.positionConcentrationPct / risk.maxPositionConcentrationPct) * 100}%` }}
            />
          </div>
        </div>

        {/* Class Exposure */}
        <div className="p-2 rounded bg-white/[0.02] border border-white/[0.05]">
          <div className="flex justify-between text-[10px] font-mono text-slate-400">
            <span>MAX ASSET CLASS EXPOSURE</span>
            <span className="text-slate-500">LIMIT: {risk.maxClassExposurePct}%</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-sm font-mono-num font-bold text-white">
              {risk.classExposurePct.toFixed(1)}%
            </span>
            <span className="text-[10px] font-mono text-emerald-400">PASSED</span>
          </div>
          <div className="w-full h-1 bg-black/40 rounded-full mt-1 overflow-hidden">
            <div 
              className="h-full bg-indigo-400 rounded-full"
              style={{ width: `${(risk.classExposurePct / risk.maxClassExposurePct) * 100}%` }}
            />
          </div>
        </div>

        {/* Correlation Exposure */}
        <div className="p-2 rounded bg-white/[0.02] border border-white/[0.05]">
          <div className="flex justify-between text-[10px] font-mono text-slate-400">
            <span>PORTFOLIO CORRELATION</span>
            <span className="text-slate-500">CAP: {risk.maxCorrelationExposure.toFixed(2)}</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-sm font-mono-num font-bold text-white">
              {risk.correlationExposure.toFixed(2)}
            </span>
            <span className="text-[10px] font-mono text-emerald-400">PASSED</span>
          </div>
          <div className="w-full h-1 bg-black/40 rounded-full mt-1 overflow-hidden">
            <div 
              className="h-full bg-violet-400 rounded-full"
              style={{ width: `${(risk.correlationExposure / risk.maxCorrelationExposure) * 100}%` }}
            />
          </div>
        </div>
      </div>

      {/* Interactive Stress-Test Simulator Strip */}
      <div className="mt-2.5 pt-2 border-t border-white/[0.06] flex items-center justify-between text-[11px] font-mono bg-black/20 p-2 rounded">
        <div className="flex items-center gap-2">
          <Zap className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-slate-400">STRESS-TEST SHOCK SIMULATOR:</span>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="range"
            min="0"
            max="2.5"
            step="0.1"
            value={stressDelta}
            onChange={(e) => setStressDelta(parseFloat(e.target.value))}
            className="w-32 accent-amber-400 cursor-pointer"
          />
          <span className="text-amber-300 font-mono-num w-16 text-right">
            +{stressDelta.toFixed(1)}% DD
          </span>
          {stressDelta > 0 && (
            <button
              onClick={() => setStressDelta(0)}
              className="text-[10px] text-slate-400 hover:text-white px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.08]"
            >
              RESET
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
