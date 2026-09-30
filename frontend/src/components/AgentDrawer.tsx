import React from 'react';
import { AgentNode } from '../types';
import { 
  X, 
   
   
  Award, 
   
   
   
  

} from 'lucide-react';

interface AgentDrawerProps {
  agent: AgentNode | null;
  onClose: () => void;
  onAdjustWeight?: (agentId: string, delta: number) => void;
}

export const AgentDrawer: React.FC<AgentDrawerProps> = ({
  agent,
  onClose,
  onAdjustWeight,
}) => {
  if (!agent) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm flex justify-end animate-fade-in">
      <div className="w-full max-w-xl bg-[#0d0f17] border-l border-white/[0.1] h-full shadow-2xl flex flex-col justify-between p-6 font-mono overflow-y-auto">
        {/* Drawer Header */}
        <div>
          <div className="flex items-center justify-between pb-4 border-b border-white/[0.08]">
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded bg-cyan-400 shadow-[0_0_8px_#00f0ff]"></div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-white tracking-tight">{agent.name}</h2>
                  <span className="text-xs px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-semibold">
                    {agent.role}
                  </span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  MODEL: <strong className="text-slate-200">{agent.modelsUsed[0] ?? '—'}</strong>
                </div>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Reputation & Confidence Banner */}
          <div className="grid grid-cols-2 gap-3 my-4">
            <div className="p-3 rounded bg-white/[0.02] border border-white/[0.06]">
              <div className="text-[10px] text-slate-400 flex items-center gap-1">
                <Award className="w-3 h-3 text-cyan-400" />
                REPUTATION SCORE
              </div>
              <div className="text-2xl font-mono-num font-bold text-white mt-1">
                {agent.reputationScore.toFixed(2)} / 1.00
              </div>
              <div className="text-[10px] text-emerald-400 mt-0.5">TOP 5% IN MULTI-AGENT POOL</div>
            </div>

            <div className="p-3 rounded bg-white/[0.02] border border-white/[0.06]">
              <div className="text-[10px] text-slate-400">WIN RATE ACCURACY</div>
              <div className="text-2xl font-mono-num font-bold text-emerald-400 mt-1">
                {agent.recentAccuracyPct.toFixed(1)}%
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">ROLLING 90-DAY WINDOW</div>
            </div>
          </div>

          {/* Current Thesis */}
          <div className="p-3.5 rounded bg-cyan-950/20 border border-cyan-800/40 space-y-2">
            <div className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold">
              CURRENT FORMAL THESIS
            </div>
            <p className="text-sm text-slate-200 leading-relaxed font-sans">
              "{agent.currentThesis}"
            </p>
            <div className="flex items-center justify-between text-xs pt-2 border-t border-white/[0.06]">
              <span className="text-slate-400">THESIS CONFIDENCE:</span>
              <span className="text-cyan-300 font-bold font-mono-num">{agent.confidencePct}%</span>
            </div>
          </div>

          {/* Governance & Specifications */}
          <div className="mt-4 p-3.5 rounded bg-black/40 border border-white/[0.06] space-y-2.5 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-400">INFERENCE LATENCY:</span>
              <span className="text-slate-200 font-mono-num">{agent.latencyMs} ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">CURRENT BIAS:</span>
              <span className={`font-semibold ${
                agent.bias === 'BULL' ? 'text-emerald-400' : agent.bias === 'BEAR' ? 'text-rose-400' : 'text-slate-300'
              }`}>{agent.bias}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">STATUS:</span>
              <span className="text-emerald-400 font-medium uppercase">{agent.status}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">SYSTEM PROMPT PIN:</span>
              <span className="text-slate-500">— (not published)</span>
            </div>
          </div>

          {/* Gated Consensus Thresholds */}
          <div className="mt-4 p-3 rounded bg-white/[0.02] border border-white/[0.06] space-y-2 text-xs">
            <div className="text-[10px] text-slate-400 uppercase tracking-wider">
              CONSTITUTIONAL GATES
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Consensus Minimum:</span>
              <span className="text-slate-500">— (see Settings)</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Adversarial Challenger Requirement:</span>
              <span className="text-slate-500">— (see Settings)</span>
            </div>
          </div>
        </div>

        {/* Action Controls Footer */}
        <div className="mt-6 pt-4 border-t border-white/[0.08] space-y-2">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">
            AGENT SUPERVISION
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => onAdjustWeight && onAdjustWeight(agent.id, 0.05)}
              className="py-2 px-3 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs text-slate-200 hover:text-white transition-all font-semibold"
            >
              BOOST REPUTATION (+5%)
            </button>
            <button
              onClick={() => onAdjustWeight && onAdjustWeight(agent.id, -0.05)}
              className="py-2 px-3 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs text-slate-200 hover:text-white transition-all font-semibold"
            >
              DAMPEN WEIGHT (-5%)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
