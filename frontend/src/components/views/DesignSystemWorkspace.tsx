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
    { name: 'OLED Black Canvas', hex: '#050608', css: '--bg-dark', desc: 'Primary deep institutional background' },
    { name: 'Charcoal Panel', hex: '#0d0f17', css: '--panel-dark', desc: 'Primary container surface' },
    { name: 'Electric Cyan', hex: '#00f0ff', css: '--accent-cyan', desc: 'Primary signature intelligence accent' },
    { name: 'Soft Indigo / Violet', hex: '#818cf8', css: '--accent-violet', desc: 'Secondary macro / benchmark accent' },
    { name: 'Institutional Emerald', hex: '#10b981', css: '--accent-emerald', desc: 'Controlled positive P&L / verification' },
    { name: 'Firewall Amber', hex: '#f59e0b', css: '--accent-amber', desc: 'Warning threshold / caution state' },
    { name: 'Halt Rose / Red', hex: '#f43f5e', css: '--accent-rose', desc: 'Emergency halt / critical drawdown' },
  ];

  return (
    <div className="space-y-6 pb-16 font-mono text-xs">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Palette className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              AIOS-0X INSTITUTIONAL REUSABLE DESIGN SYSTEM
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              DESIGN SYSTEM CATALOG
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Component Tokens • Typographic Scales • High-Density Operational Patterns
          </div>
        </div>

        <div className="text-slate-400 text-xs">
          TOKEN REGISTRY: <strong className="text-cyan-300">FIGMA RATIFIED v1.0</strong>
        </div>
      </div>

      {/* 1. COLOR SYSTEM */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-3">
        <div className="flex items-center gap-2 pb-2 border-b border-white/[0.06]">
          <Palette className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-bold uppercase text-white tracking-wider">
            1. COLOR PALETTE & ATMOSPHERIC TOKENS
          </h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {colors.map((c) => (
            <div
              key={c.hex}
              onClick={() => handleCopy(c.hex)}
              className="p-3 rounded bg-white/[0.02] border border-white/[0.05] hover:border-cyan-500/40 cursor-pointer transition-all group"
            >
              <div className="w-full h-12 rounded border border-white/[0.1] mb-2 flex items-end p-1.5 justify-end shadow-inner" style={{ backgroundColor: c.hex }}>
                <span className="text-[9px] px-1 rounded bg-black/60 text-white font-mono">
                  {copiedToken === c.hex ? 'COPIED!' : c.hex}
                </span>
              </div>
              <div className="font-bold text-white group-hover:text-cyan-300 text-xs">{c.name}</div>
              <div className="text-[10px] text-slate-400 mt-0.5">{c.desc}</div>
              <div className="text-[9px] text-cyan-400/80 mt-1 font-mono">{c.css}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 2. TYPOGRAPHY */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-3">
        <div className="flex items-center gap-2 pb-2 border-b border-white/[0.06]">
          <Type className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-bold uppercase text-white tracking-wider">
            2. TYPOGRAPHY & TABULAR NUMERAL PATTERNS
          </h3>
        </div>

        <div className="space-y-3 font-sans">
          <div className="p-3 rounded bg-white/[0.02] border border-white/[0.05]">
            <div className="text-[10px] font-mono text-slate-400 mb-1">DISPLAY NUMERALS (font-mono-num font-bold)</div>
            <div className="text-3xl font-mono-num font-bold text-white tracking-tight">
              $144,280,000.00 <span className="text-sm font-medium text-emerald-400 font-mono">+1.28%</span>
            </div>
          </div>

          <div className="p-3 rounded bg-white/[0.02] border border-white/[0.05]">
            <div className="text-[10px] font-mono text-slate-400 mb-1">SECTION HEADINGS (font-mono text-xs font-bold uppercase tracking-wider)</div>
            <div className="font-mono text-xs font-bold uppercase tracking-wider text-slate-100">
              PORTFOLIO TRAJECTORY & VALUE-AT-RISK ENGINE
            </div>
          </div>

          <div className="p-3 rounded bg-white/[0.02] border border-white/[0.05]">
            <div className="text-[10px] font-mono text-slate-400 mb-1">DATA LABELS & MONOSPACE CODE (font-mono text-[11px])</div>
            <div className="font-mono text-[11px] text-slate-300">
              SHA-256 HASH: 7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d904b
            </div>
          </div>
        </div>
      </div>

      {/* 3. BUTTONS & CONTROLS */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-3">
        <div className="flex items-center gap-2 pb-2 border-b border-white/[0.06]">
          <Zap className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-bold uppercase text-white tracking-wider">
            3. INSTITUTIONAL BUTTON & CONTROL TOKENS
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button className="px-4 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-black text-xs font-bold font-mono transition-all shadow-[0_0_12px_rgba(0,240,255,0.4)]">
            PRIMARY ACTION
          </button>

          <button className="px-4 py-2 rounded bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-700/60 text-cyan-300 text-xs font-bold font-mono transition-all shadow-[0_0_8px_rgba(0,240,255,0.15)]">
            SECONDARY ACTION
          </button>

          <button className="px-4 py-2 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-slate-300 hover:text-white text-xs font-mono transition-all">
            TERTIARY NEUTRAL
          </button>

          <button className="px-4 py-2 rounded bg-red-950/80 hover:bg-red-900 border border-red-700/60 text-red-300 hover:text-white text-xs font-bold font-mono transition-all shadow-[0_0_10px_rgba(239,68,68,0.25)]">
            KILL SWITCH / DESTRUCTIVE
          </button>
        </div>
      </div>

      {/* 4. STATUS INDICATORS */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-3">
        <div className="flex items-center gap-2 pb-2 border-b border-white/[0.06]">
          <Activity className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-bold uppercase text-white tracking-wider">
            4. STATUS PILLS & BADGES
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-emerald-950/40 text-emerald-400 border border-emerald-800/40 text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
            <span>SYSTEM NOMINAL</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800 text-[11px]">
            <span>AUTONOMY: SUPERVISED</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 text-[11px]">
            <span>TIER 1 WARNING</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-red-950 text-red-400 border border-red-800 text-[11px]">
            <span>EMERGENCY HALT</span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800 text-[11px]">
            <span>COMPLIANCE SIGN-OFF PENDING</span>
          </div>
        </div>
      </div>
    </div>
  );
};
