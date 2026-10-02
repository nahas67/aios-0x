import React, { useState } from 'react';
import { 
  Palette, 
  Type, 
   
   
  Zap, 
   
  Activity, 
   
   
   
   
   

} from 'lucide-react';

export const DesignSystemWorkspace: React.FC = () => {
  const [copiedToken, setCopiedToken] = useState<string | null>(null);

  const handleCopy = (token: string) => {
    navigator.clipboard.writeText(token);
    setCopiedToken(token);
    setTimeout(() => setCopiedToken(null), 1500);
  };

  const colors = [
    { name: 'OLED Black Canvas', hex: 'var(--color-surface-deep)', css: '--bg-dark', desc: 'Primary deep institutional background' },
    { name: 'Charcoal Panel', hex: 'var(--color-surface-1)', css: '--panel-dark', desc: 'Primary container surface' },
    { name: 'Electric Cyan', hex: 'var(--color-accent)', css: '--accent-accent', desc: 'Primary signature intelligence accent' },
    { name: 'Soft Indigo / Violet', hex: 'var(--color-violet)', css: '--accent-violet', desc: 'Secondary macro / benchmark accent' },
    { name: 'Institutional Emerald', hex: 'var(--color-positive)', css: '--accent-positive', desc: 'Controlled positive P&L / verification' },
    { name: 'Firewall Amber', hex: 'var(--color-warning)', css: '--accent-warning', desc: 'Warning threshold / caution state' },
    { name: 'Halt Rose / Red', hex: 'var(--color-destructive)', css: '--accent-destructive', desc: 'Emergency halt / critical drawdown' },
  ];

  return (
    <div className="space-y-6 pb-16 font-mono text-xs">
      {/* Header */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Palette className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              AIOS-0X INSTITUTIONAL REUSABLE DESIGN SYSTEM
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
              DESIGN SYSTEM CATALOG
            </span>
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            Component Tokens â€¢ Typographic Scales â€¢ High-Density Operational Patterns
          </div>
        </div>

        <div className="text-text-muted text-xs">
          TOKEN REGISTRY: <strong className="text-accent">FIGMA RATIFIED v1.0</strong>
        </div>
      </div>

      {/* 1. COLOR SYSTEM */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl space-y-3">
        <div className="flex items-center gap-2 pb-2 border-b border-border-subtle">
          <Palette className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
            1. COLOR PALETTE & ATMOSPHERIC TOKENS
          </h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {colors.map((c) => (
            <div
              key={c.hex}
              onClick={() => handleCopy(c.hex)}
              className="p-3 rounded bg-surface-veil border border-border-subtle hover:border-accent cursor-pointer transition-all group"
            >
              <div className="w-full h-12 rounded border border-border-strong mb-2 flex items-end p-1.5 justify-end shadow-inner" style={{ backgroundColor: c.hex }}>
                <span className="text-[9px] px-1 rounded bg-surface-deep text-text-strong font-mono">
                  {copiedToken === c.hex ? 'COPIED!' : c.hex}
                </span>
              </div>
              <div className="font-bold text-text-strong group-hover:text-accent text-xs">{c.name}</div>
              <div className="text-[10px] text-text-muted mt-0.5">{c.desc}</div>
              <div className="text-[9px] text-accent mt-1 font-mono">{c.css}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 2. TYPOGRAPHY */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl space-y-3">
        <div className="flex items-center gap-2 pb-2 border-b border-border-subtle">
          <Type className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
            2. TYPOGRAPHY & TABULAR NUMERAL PATTERNS
          </h3>
        </div>

        <div className="space-y-3 font-sans">
          <div className="p-3 rounded bg-surface-veil border border-border-subtle">
            <div className="text-[10px] font-mono text-text-muted mb-1">DISPLAY NUMERALS (font-mono-num font-bold)</div>
            <div className="text-3xl font-mono-num font-bold text-text-strong tracking-tight">
              $144,280,000.00 <span className="text-sm font-medium text-positive font-mono">+1.28%</span>
            </div>
          </div>

          <div className="p-3 rounded bg-surface-veil border border-border-subtle">
            <div className="text-[10px] font-mono text-text-muted mb-1">SECTION HEADINGS (font-mono text-xs font-bold uppercase tracking-wider)</div>
            <div className="font-mono text-xs font-bold uppercase tracking-wider text-text-strong">
              PORTFOLIO TRAJECTORY & VALUE-AT-RISK ENGINE
            </div>
          </div>

          <div className="p-3 rounded bg-surface-veil border border-border-subtle">
            <div className="text-[10px] font-mono text-text-muted mb-1">DATA LABELS & MONOSPACE CODE (font-mono text-[11px])</div>
            <div className="font-mono text-[11px] text-text">
              SHA-256 HASH: 7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d904b
            </div>
          </div>
        </div>
      </div>

      {/* 3. BUTTONS & CONTROLS */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl space-y-3">
        <div className="flex items-center gap-2 pb-2 border-b border-border-subtle">
          <Zap className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
            3. INSTITUTIONAL BUTTON & CONTROL TOKENS
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button className="px-4 py-2 rounded bg-accent hover:bg-accent text-text-strong text-xs font-bold font-mono transition-all shadow-[0_0_12px_rgba(0,240,255,0.4)]">
            PRIMARY ACTION
          </button>

          <button className="px-4 py-2 rounded bg-info-bg hover:bg-info-bg border border-accent text-accent text-xs font-bold font-mono transition-all shadow-[0_0_8px_rgba(0,240,255,0.15)]">
            SECONDARY ACTION
          </button>

          <button className="px-4 py-2 rounded bg-surface-veil hover:bg-surface-raised border border-border-strong text-text hover:text-text-strong text-xs font-mono transition-all">
            TERTIARY NEUTRAL
          </button>

          <button className="px-4 py-2 rounded bg-destructive hover:bg-destructive border border-destructive text-destructive hover:text-text-strong text-xs font-bold font-mono transition-all shadow-[0_0_10px_rgba(239,68,68,0.25)]">
            KILL SWITCH / DESTRUCTIVE
          </button>
        </div>
      </div>

      {/* 4. STATUS INDICATORS */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl space-y-3">
        <div className="flex items-center gap-2 pb-2 border-b border-border-subtle">
          <Activity className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
            4. STATUS PILLS & BADGES
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-positive-bg text-positive border border-positive text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full bg-positive animate-ping"></span>
            <span>SYSTEM NOMINAL</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-info-bg text-accent border border-accent text-[11px]">
            <span>AUTONOMY: SUPERVISED</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-warning-bg text-warning border border-warning text-[11px]">
            <span>TIER 1 WARNING</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-destructive text-destructive border border-destructive text-[11px]">
            <span>EMERGENCY HALT</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-violet text-violet border border-violet text-[11px]">
            <span>COMPLIANCE SIGN-OFF PENDING</span>
          </div>
        </div>
      </div>
    </div>
  );
};
