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
import { AutonomyLevel, ExecutionMode, WorkspaceTab } from '../types';

interface TopSystemBarProps {
  autonomy: AutonomyLevel;
  onAutonomyChange: (level: AutonomyLevel) => void;
  executionMode: ExecutionMode;
  onExecutionModeToggle: () => void;
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
  executionMode,
  onExecutionModeToggle,
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
        return 'bg-cyan-950/80 text-cyan-400 border-cyan-700/50';
      case 'SUPERVISED':
        return 'bg-emerald-950/80 text-emerald-400 border-emerald-700/50';
      case 'ASSISTED':
        return 'bg-blue-950/80 text-blue-400 border-blue-700/50';
      case 'MANUAL':
        return 'bg-slate-900 text-slate-300 border-slate-700';
      case 'EMERGENCY_HALT':
        return 'bg-red-950 text-red-400 border-red-700 animate-pulse';
      default:
        return 'bg-slate-900 text-slate-300 border-slate-700';
    }
  };

  return (
    <header className="sticky top-0 z-40 h-11 w-full bg-[#090a0f]/95 backdrop-blur-md border-b border-white/[0.07] px-3 flex items-center justify-between text-xs font-mono select-none">
      {/* Left: Brand + System State */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 pr-3 border-r border-white/[0.08]">
          <div className="w-2.5 h-2.5 rounded-sm bg-gradient-to-tr from-cyan-500 to-cyan-300 shadow-[0_0_8px_rgba(0,240,255,0.6)] flex items-center justify-center">
            <div className="w-1 h-1 bg-[#090a0f] rounded-full"></div>
          </div>
          <span className="font-bold tracking-wider text-sm bg-gradient-to-r from-slate-100 to-slate-400 bg-clip-text text-transparent">
            AIOS-0X
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-400 border border-white/[0.06] tracking-tight">
            v1.0.0-RATIFIED
          </span>
        </div>

        {/* Status Pills */}
        <div className="hidden lg:flex items-center gap-2">
          {/* Nominal Status */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-950/40 text-emerald-400 border border-emerald-800/40 text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
            <span className="font-medium tracking-wide">SYSTEM NOMINAL</span>
          </div>

          {/* Market Status */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-white/[0.03] text-slate-300 border border-white/[0.06] text-[11px]">
            <Activity className="w-3 h-3 text-cyan-400" />
            <span>MARKET OPEN</span>
          </div>

          {/* Audit Chain (derived from /audit/verify, never assumed) */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-white/[0.03] text-slate-300 border border-white/[0.06] text-[11px]">
            <ShieldCheck className={`w-3 h-3 ${chainVerified === true ? 'text-emerald-400' : chainVerified === false ? 'text-rose-400' : 'text-slate-500'}`} />
            <span>{chainVerified === true ? 'AUDIT VERIFIED' : chainVerified === false ? 'AUDIT BROKEN' : 'AUDIT UNKNOWN'}</span>
          </div>

          {/* Risk Level (null while /risk has not answered) */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-white/[0.03] text-slate-300 border border-white/[0.06] text-[11px]">
            <span className="text-slate-500">RISK:</span>
            <span className="font-mono text-cyan-300">{drawdownPct !== null ? `${drawdownPct.toFixed(2)}% DD` : '—'}</span>
            {drawdownPct !== null && (
              <span className="text-[9px] px-1 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/50 uppercase">
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
          className="w-full flex items-center justify-between px-3 py-1 rounded bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.07] text-slate-400 hover:text-slate-200 transition-colors text-left"
        >
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-[11px] font-sans text-slate-400">Search symbols, decisions, agents, constitution...</span>
          </div>
          <kbd className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/40 border border-white/[0.08] text-slate-400">
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
            <div className="absolute right-0 mt-1 w-52 rounded-md bg-[#0d0f17] border border-white/[0.1] shadow-2xl p-1 z-50 text-[11px]">
              <div className="px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-slate-500 border-b border-white/[0.06]">
                Operational Governance
              </div>
              {(['MANUAL', 'ASSISTED', 'SUPERVISED', 'AUTONOMOUS'] as AutonomyLevel[]).map((level) => (
                <button
                  key={level}
                  onClick={() => {
                    onAutonomyChange(level);
                    setIsAutonomyDropdownOpen(false);
                  }}
                  className={`w-full text-left px-2 py-1.5 rounded flex items-center justify-between hover:bg-white/[0.05] transition-colors ${
                    autonomy === level ? 'text-cyan-400 bg-white/[0.04]' : 'text-slate-300'
                  }`}
                >
                  <span className="font-mono">{level}</span>
                  {autonomy === level && <CheckCircle2 className="w-3 h-3 text-cyan-400" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Live / Paper Switch */}
        <button
          onClick={onExecutionModeToggle}
          className={`flex items-center gap-1.5 px-2 py-0.5 rounded border text-[11px] font-mono transition-colors ${
            executionMode === 'LIVE'
              ? 'bg-amber-950/60 text-amber-300 border-amber-600/60 shadow-[0_0_8px_rgba(245,158,11,0.2)]'
              : 'bg-white/[0.03] text-cyan-400 border-cyan-700/40'
          }`}
          title="Toggle between Paper Trading and Gated Live Trading"
        >
          <span className={`w-1.5 h-1.5 rounded-full ${executionMode === 'LIVE' ? 'bg-amber-400 animate-pulse' : 'bg-cyan-400'}`}></span>
          <span>{executionMode}</span>
        </button>

        {/* UTC Clock */}
        <div className="hidden sm:flex items-center gap-1 text-slate-400 font-mono text-[11px] px-2 py-0.5 bg-black/30 rounded border border-white/[0.05]">
          <Clock className="w-3 h-3 text-slate-500" />
          <span>{utcTime || '16:22:00 UTC'}</span>
        </div>

        {/* Settings Button */}
        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className={`flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] font-mono transition-colors ${
              activeTab === 'settings'
                ? 'bg-cyan-950 text-cyan-300 border-cyan-500 shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                : 'bg-white/[0.03] text-slate-300 hover:text-white border-white/[0.08] hover:bg-white/[0.06]'
            }`}
            title="Open Master System Configuration & Risk Rules"
          >
            <SettingsIcon className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden md:inline">SETTINGS</span>
          </button>
        )}

        {/* Emergency Kill Switch */}
        <button
          onClick={onTriggerKillSwitch}
          className="flex items-center gap-1.5 px-2.5 py-0.5 rounded bg-red-950/80 hover:bg-red-900 border border-red-700/60 text-red-300 font-mono text-[11px] font-semibold tracking-wider hover:text-white transition-all shadow-[0_0_10px_rgba(239,68,68,0.25)] active:scale-95"
          title="Emergency Protocol: Flatten positions and halt autonomous execution"
        >
          <Power className="w-3 h-3 text-red-400" />
          <span>KILL SWITCH</span>
        </button>
      </div>
    </header>
  );
};
