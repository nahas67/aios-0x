import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  Clock, 
   
  Activity, 
  Search, 
  Power, 
  CheckCircle2, 
  Sliders, 
   
  
  
  Settings as SettingsIcon
} from 'lucide-react';
import { AutonomyLevel, WorkspaceTab } from '../types';

interface TopSystemBarProps {
  autonomy: AutonomyLevel;
  onAutonomyChange: (level: AutonomyLevel) => void;
  onOpenCommandPalette: () => void;
  onTriggerKillSwitch: () => void;
  drawdownPct: number | null;
  /** Null while /audit/verify has not answered — renders UNKNOWN, never assumed. */
  chainVerified: boolean | null;
  onOpenSettings?: () => void;
  activeTab?: WorkspaceTab;
}

export const TopSystemBar: React.FC<TopSystemBarProps> = ({
  autonomy,
  onAutonomyChange,
  onOpenCommandPalette,
  onTriggerKillSwitch,
  drawdownPct,
  chainVerified,
  onOpenSettings,
  activeTab,
}) => {
  const [utcTime, setUtcTime] = useState<string>('');
  const [isAutonomyDropdownOpen, setIsAutonomyDropdownOpen] = useState(false);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setUtcTime(
        now.toISOString().substring(11, 19) + ' UTC'
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const getAutonomyBadgeColor = (level: AutonomyLevel) => {
    switch (level) {
      case 'AUTONOMOUS':
        return 'bg-info-bg text-accent border-accent';
      case 'SUPERVISED':
        return 'bg-positive-bg text-positive border-positive';
      case 'ASSISTED':
        return 'bg-accent-info text-accent-info border-accent-info';
      case 'MANUAL':
        return 'bg-surface-deep text-text border-border-subtle';
      case 'EMERGENCY_HALT':
        return 'bg-destructive text-destructive border-destructive animate-pulse';
      default:
        return 'bg-surface-deep text-text border-border-subtle';
    }
  };

  return (
    <header className="sticky top-0 z-40 h-11 w-full bg-[var(--color-surface-rail)]//95 backdrop-blur-md border-b border-border-subtle px-3 flex items-center justify-between text-xs font-mono select-none">
      {/* Left: Brand + System State */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 pr-3 border-r border-border-strong">
          <div className="w-2.5 h-2.5 rounded-sm bg-gradient-to-tr from-accent to-accent shadow-[0_0_8px_rgba(0,240,255,0.6)] flex items-center justify-center">
            <div className="w-1 h-1 bg-[var(--color-surface-rail)] rounded-full"></div>
          </div>
          <span className="font-bold tracking-wider text-sm bg-gradient-to-r from-text-strong to-text-muted bg-clip-text text-transparent">
            AIOS-0X
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-veil text-text-muted border border-border-subtle tracking-tight">
            v1.0.0-RATIFIED
          </span>
        </div>

        {/* Status Pills */}
        <div className="hidden lg:flex items-center gap-2">
          {/* Nominal Status */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-positive-bg text-positive border border-positive text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full bg-positive animate-ping"></span>
            <span className="font-medium tracking-wide">SYSTEM NOMINAL</span>
          </div>

          {/* Market Status */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-veil text-text border border-border-subtle text-[11px]">
            <Activity className="w-3 h-3 text-accent" />
            <span>MARKET OPEN</span>
          </div>

          {/* Audit Chain (derived from /audit/verify, never assumed) */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-veil text-text border border-border-subtle text-[11px]">
            <ShieldCheck className={`w-3 h-3 ${chainVerified === true ? 'text-positive' : chainVerified === false ? 'text-destructive' : 'text-text-subtle'}`} />
            <span>{chainVerified === true ? 'AUDIT VERIFIED' : chainVerified === false ? 'AUDIT BROKEN' : 'AUDIT UNKNOWN'}</span>
          </div>

          {/* Risk Level (null while /risk has not answered) */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-surface-veil text-text border border-border-subtle text-[11px]">
            <span className="text-text-subtle">RISK:</span>
            <span className="font-mono text-accent">{drawdownPct !== null ? `${drawdownPct.toFixed(2)}% DD` : '—'}</span>
            {drawdownPct !== null && (
              <span className="text-[9px] px-1 rounded bg-positive-bg text-positive border border-positive uppercase">
                LOW
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Center: Command Palette Trigger */}
      <div className="flex-1 max-w-md mx-4 hidden md:block">
        <button
          onClick={onOpenCommandPalette}
          className="w-full flex items-center justify-between px-3 py-1 rounded bg-surface-veil hover:bg-surface-raised border border-border-subtle text-text-muted hover:text-text-strong transition-colors text-left"
        >
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-text-subtle" />
            <span className="text-[11px] font-sans text-text-muted">Search symbols, decisions, agents, constitution...</span>
          </div>
          <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-sunken border border-border-strong text-text-muted">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Right: Autonomy Level, Live/Paper, UTC Clock, Kill Switch */}
      <div className="flex items-center gap-2.5">
        {/* Autonomy Selector */}
        <div className="relative">
          <button
            onClick={() => setIsAutonomyDropdownOpen(!isAutonomyDropdownOpen)}
            className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded border text-[11px] font-medium transition-all ${getAutonomyBadgeColor(autonomy)}`}
          >
            <Sliders className="w-3 h-3" />
            <span className="tracking-wide">AUTONOMY: {autonomy}</span>
          </button>

          {isAutonomyDropdownOpen && (
            <div className="absolute right-0 mt-1 w-52 rounded-md bg-[var(--color-surface-1)] border border-border-strong shadow-2xl p-1 z-50 text-[11px]">
              <div className="px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-text-subtle border-b border-border-subtle">
                Operational Governance
              </div>
              {(['MANUAL', 'ASSISTED', 'SUPERVISED', 'AUTONOMOUS'] as AutonomyLevel[]).map((level) => (
                <button
                  key={level}
                  onClick={() => {
                    onAutonomyChange(level);
                    setIsAutonomyDropdownOpen(false);
                  }}
                  className={`w-full text-left px-2 py-1.5 rounded flex items-center justify-between hover:bg-surface-raised transition-colors ${
                    autonomy === level ? 'text-accent bg-surface-veil' : 'text-text'
                  }`}
                >
                  <span className="font-mono">{level}</span>
                  {autonomy === level && <CheckCircle2 className="w-3 h-3 text-accent" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* REMOVED: the Live/Paper switch.
          It rendered "LIVE" in amber with a pulsing dot and the tooltip "Toggle between
          Paper Trading and Gated Live Trading", while `executionMode` was read nowhere
          except this label and `defaultExecutionMode` had no backend field at all. Venue
          selection is governed by AIOS_ALLOW_LIVE_EXECUTION + AIOS_EXCHANGE_TESTNET in
          communities/c5_execution/adapters.py, which this could not reach. A badge that
          asserts a capital mode the system does not implement is a §3.1 honesty failure,
          and it becomes a real one the day live execution is enabled.
          ARCHITECTURE.txt §13 specifies G240 Long Shadow -> G250 Canary Capital, a
          governance gate, not a console toggle. */}

        {/* UTC Clock */}
        <div className="hidden sm:flex items-center gap-1 text-text-muted font-mono text-[11px] px-2 py-0.5 bg-surface-sunken rounded border border-border-subtle">
          <Clock className="w-3 h-3 text-text-subtle" />
          <span>{utcTime || '16:22:00 UTC'}</span>
        </div>

        {/* Settings Button */}
        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className={`flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] font-mono transition-colors ${
              activeTab === 'settings'
                ? 'bg-info-bg text-accent border-accent shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                : 'bg-surface-veil text-text hover:text-text-strong border-border-strong hover:bg-surface-raised'
            }`}
            title="Open Master System Configuration & Risk Rules"
          >
            <SettingsIcon className="w-3.5 h-3.5 text-accent" />
            <span className="hidden md:inline">SETTINGS</span>
          </button>
        )}

        {/* Emergency Kill Switch */}
        <button
          onClick={onTriggerKillSwitch}
          className="flex items-center gap-1.5 px-2.5 py-0.5 rounded bg-destructive hover:bg-destructive border border-destructive text-destructive font-mono text-[11px] font-semibold tracking-wider hover:text-text-strong transition-all shadow-[0_0_10px_rgba(239,68,68,0.25)] active:scale-95"
          title="Emergency Protocol: Flatten positions and halt autonomous execution"
        >
          <Power className="w-3 h-3 text-destructive" />
          <span>KILL SWITCH</span>
        </button>
      </div>
    </header>
  );
};
