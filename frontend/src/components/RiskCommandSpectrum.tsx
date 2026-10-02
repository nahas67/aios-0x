import React from 'react';
import { RiskSpectrum } from '../types';
import { ShieldAlert } from 'lucide-react';

interface RiskCommandSpectrumProps {
  risk: RiskSpectrum;
  /** Spectrum fields the backend does not compute; rendered as "—". */
  notComputed?: string[];
  onOpenRiskDrawer?: () => void;
  className?: string;
}

export const RiskCommandSpectrum: React.FC<RiskCommandSpectrumProps> = ({
  risk,
  notComputed = [],
  onOpenRiskDrawer,
  className = '',
}) => {
  const unknown = (field: string) => notComputed.includes(field);
  const effectiveDd = Math.max(0, risk.currentDrawdownPct);

  const getStatusLevel = (dd: number) => {
    if (dd >= risk.emergencyHaltPct) return { text: 'EMERGENCY HALT (KILL SWITCH)', color: 'text-destructive bg-destructive border-destructive' };
    if (dd >= risk.reductionThresholdPct) return { text: 'TIER-2 REDUCTION (50% CUT)', color: 'text-warning bg-warning-bg border-warning' };
    if (dd >= risk.warningThresholdPct) return { text: 'TIER-1 WARNING (25% CUT)', color: 'text-warning bg-warning-bg border-warning' };
    return { text: 'CONSTITUTIONALLY NOMINAL', color: 'text-positive bg-positive-bg border-positive' };
  };

  const status = getStatusLevel(effectiveDd);

  // Scaled percentage along 0% to 3.5% spectrum bar
  const maxScale = 3.5;
  const currentPosPct = Math.min(100, (effectiveDd / maxScale) * 100);
  const warningPosPct = (risk.warningThresholdPct / maxScale) * 100;
  const reductionPosPct = (risk.reductionThresholdPct / maxScale) * 100;
  const haltPosPct = (risk.emergencyHaltPct / maxScale) * 100;

  return (
    <div className={`bg-[var(--color-surface-1)] border border-border-strong rounded-md p-3.5 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-text-strong uppercase">
            PORTFOLIO RISK COMMAND
          </h3>
          <span className={`text-[9px] font-mono px-2 py-0.5 rounded border font-semibold ${status.color}`}>
            {status.text}
          </span>
        </div>

        {onOpenRiskDrawer && (
          <button
            onClick={onOpenRiskDrawer}
            className="text-[11px] font-mono text-accent hover:text-accent flex items-center gap-1"
          >
            <span>INSPECT FIREWALL</span>
            <span>→</span>
          </button>
        )}
      </div>

      {/* The Continuous Risk Spectrum Bar */}
      <div className="py-3">
        <div className="flex items-center justify-between text-[10px] font-mono text-text-muted pb-1.5">
          <span className="flex items-center gap-1">
            <span className="text-text-subtle">OPERATIONAL STATE:</span>
            <span className="text-text-strong font-mono-num font-bold text-xs">{effectiveDd.toFixed(2)}% DD</span>
          </span>
          <span className="text-text-subtle">
            BUFFER TO HALT: <span className="text-accent font-mono-num font-bold">{(risk.emergencyHaltPct - effectiveDd).toFixed(2)}%</span>
          </span>
        </div>

        {/* Continuous Spectrum Track */}
        <div className="relative h-6 w-full rounded bg-surface-deep border border-border-strong overflow-hidden p-0.5 flex">
          {/* Zone 1: Nominal (Green) */}
          <div 
            style={{ width: `${warningPosPct}%` }}
            className="h-full bg-gradient-to-r from-positive to-positive border-r border-positive flex items-center justify-start pl-2"
          >
            <span className="text-[9px] font-mono text-positive uppercase">NOMINAL</span>
          </div>

          {/* Zone 2: Warning (Yellow/Amber) */}
          <div 
            style={{ width: `${reductionPosPct - warningPosPct}%` }}
            className="h-full bg-gradient-to-r from-warning to-warning border-r border-warning flex items-center justify-center"
          >
            <span className="text-[9px] font-mono text-warning uppercase">WARN</span>
          </div>

          {/* Zone 3: Reduction (Orange/Red) */}
          <div 
            style={{ width: `${haltPosPct - reductionPosPct}%` }}
            className="h-full bg-gradient-to-r from-warning to-destructive border-r border-destructive flex items-center justify-center"
          >
            <span className="text-[9px] font-mono text-warning uppercase">REDUCE</span>
          </div>

          {/* Zone 4: Emergency Halt (Dark Red) */}
          <div 
            className="flex-1 h-full bg-destructive flex items-center justify-center"
          >
            <span className="text-[9px] font-mono text-destructive font-bold uppercase tracking-tighter">HALT</span>
          </div>

          {/* Active Current Position Needle Pin */}
          <div 
            className="absolute top-0 bottom-0 w-1 bg-surface-raised shadow-[0_0_10px_var(--color-text-strong)] z-10 transition-all duration-150"
            style={{ left: `${currentPosPct}%` }}
          >
            <div className="absolute -top-1 -left-1.5 w-4 h-2 bg-surface-raised rounded-full shadow-md" />
            <div className="absolute -bottom-1 -left-1.5 w-4 h-2 bg-surface-raised rounded-full shadow-md" />
          </div>
        </div>

        {/* Milestone Threshold Labels below bar */}
        <div className="relative w-full h-4 mt-1 text-[10px] font-mono text-text-subtle">
          <span className="absolute left-0">0.0%</span>
          <span
            className="absolute -translate-x-1/2 text-warning"
            style={{ left: `${warningPosPct}%` }}
          >
            {risk.warningThresholdPct.toFixed(2)}% Warn
          </span>
          <span
            className="absolute -translate-x-1/2 text-warning"
            style={{ left: `${reductionPosPct}%` }}
          >
            {risk.reductionThresholdPct.toFixed(2)}% Reduce
          </span>
          <span
            className="absolute -translate-x-1/2 text-destructive font-semibold"
            style={{ left: `${haltPosPct}%` }}
          >
            {risk.emergencyHaltPct.toFixed(2)}% Halt
          </span>
        </div>
      </div>

      {/* Operational Limits Matrix: Position Concentration, Class Exposure, Correlation */}
      <div className="grid grid-cols-3 gap-2.5 pt-2 border-t border-border-subtle">
        {/* Concentration */}
        <div className="p-2 rounded bg-surface-veil border border-border-subtle">
          <div className="flex justify-between text-[10px] font-mono text-text-muted">
            <span>MAX POSITION CONCENTRATION</span>
            <span className="text-text-subtle">LIMIT: {risk.maxPositionConcentrationPct}%</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-sm font-mono-num font-bold text-text-strong">
              {unknown('positionConcentrationPct') ? '—' : `${risk.positionConcentrationPct.toFixed(1)}%`}
            </span>
            <span className={`text-[10px] font-mono ${unknown('positionConcentrationPct') ? 'text-text-subtle' : 'text-positive'}`}>
              {unknown('positionConcentrationPct') ? 'NOT COMPUTED' : 'PASSED'}
            </span>
          </div>
          <div className="w-full h-1 bg-surface-sunken rounded-full mt-1 overflow-hidden">
            <div 
              className="h-full bg-accent rounded-full"
              style={{ width: `${(risk.positionConcentrationPct / risk.maxPositionConcentrationPct) * 100}%` }}
            />
          </div>
        </div>

        {/* Class Exposure */}
        <div className="p-2 rounded bg-surface-veil border border-border-subtle">
          <div className="flex justify-between text-[10px] font-mono text-text-muted">
            <span>MAX ASSET CLASS EXPOSURE</span>
            <span className="text-text-subtle">LIMIT: {risk.maxClassExposurePct}%</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-sm font-mono-num font-bold text-text-strong">
              {risk.classExposurePct.toFixed(1)}%
            </span>
            <span className="text-[10px] font-mono text-positive">PASSED</span>
          </div>
          <div className="w-full h-1 bg-surface-sunken rounded-full mt-1 overflow-hidden">
            <div 
              className="h-full bg-violet rounded-full"
              style={{ width: `${(risk.classExposurePct / risk.maxClassExposurePct) * 100}%` }}
            />
          </div>
        </div>

        {/* Correlation Exposure */}
        <div className="p-2 rounded bg-surface-veil border border-border-subtle">
          <div className="flex justify-between text-[10px] font-mono text-text-muted">
            <span>PORTFOLIO CORRELATION</span>
            <span className="text-text-subtle">CAP: {risk.maxCorrelationExposure.toFixed(2)}</span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-sm font-mono-num font-bold text-text-strong">
              {unknown('correlationExposure') ? '—' : risk.correlationExposure.toFixed(2)}
            </span>
            <span className={`text-[10px] font-mono ${unknown('correlationExposure') ? 'text-text-subtle' : 'text-positive'}`}>
              {unknown('correlationExposure') ? 'NOT COMPUTED' : 'PASSED'}
            </span>
          </div>
          <div className="w-full h-1 bg-surface-sunken rounded-full mt-1 overflow-hidden">
            <div 
              className="h-full bg-violet rounded-full"
              style={{ width: `${(risk.correlationExposure / risk.maxCorrelationExposure) * 100}%` }}
            />
          </div>
        </div>
      </div>

    </div>
  );
};
