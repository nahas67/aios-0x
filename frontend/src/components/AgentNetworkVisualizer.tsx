import React, { useState } from 'react';
import { AgentNode } from '../types';
import { 
   
  ShieldCheck, 
  BrainCircuit, 
   
   
  Scale, 
  
  TrendingUp,
  TrendingDown,

} from 'lucide-react';

interface AgentNetworkVisualizerProps {
  agents: AgentNode[];
  onSelectAgent: (agent: AgentNode) => void;
  className?: string;
}

export const AgentNetworkVisualizer: React.FC<AgentNetworkVisualizerProps> = ({
  agents,
  onSelectAgent,
  className = '',
}) => {
  const [, setHoveredAgentId] = useState<string | null>(null);

  const bullAgents = agents.filter(a => a.bias === 'BULL');
  const bearAgents = agents.filter(a => a.bias === 'BEAR');
  const neutralAgents = agents.filter(a => a.bias === 'NEUTRAL');

  return (
    <div className={`bg-[#0d0f17] border border-white/[0.08] rounded-md p-3.5 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-slate-100 uppercase">
            AI AGENT NETWORK & DEBATE TOPOLOGY
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/50">
            LANGGRAPH GATED PIPELINE
          </span>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono">
          <span className="flex items-center gap-1 text-emerald-400">
            <TrendingUp className="w-3 h-3" /> 3 BULL
          </span>
          <span className="flex items-center gap-1 text-rose-400">
            <TrendingDown className="w-3 h-3" /> 1 CHALLENGER
          </span>
          <span className="flex items-center gap-1 text-cyan-400">
            <ShieldCheck className="w-3 h-3" /> 4 VERIFIERS
          </span>
        </div>
      </div>

      {/* Main Multi-Agent Interactive Debate Field */}
      <div className="relative py-4 grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
        {/* Left Column: Bull Agents Cluster */}
        <div className="lg:col-span-4 space-y-2">
          <div className="text-[10px] font-mono uppercase tracking-wider text-emerald-400 font-semibold flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            BULLISH THESIS PROPOSERS
          </div>

          {bullAgents.map((agent) => (
            <div
              key={agent.id}
              onClick={() => onSelectAgent(agent)}
              onMouseEnter={() => setHoveredAgentId(agent.id)}
              onMouseLeave={() => setHoveredAgentId(null)}
              className="p-2 rounded bg-emerald-950/20 hover:bg-emerald-950/40 border border-emerald-800/40 hover:border-emerald-500/60 transition-all cursor-pointer shadow-sm relative group"
            >
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="font-bold text-emerald-300 group-hover:text-white">
                  {agent.name}
                </span>
                <span className="text-[10px] px-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-700/60 font-mono-num">
                  R: {agent.reputationScore.toFixed(2)}
                </span>
              </div>

              <div className="text-[10px] text-slate-300 mt-1 line-clamp-1 italic">
                "{agent.currentThesis}"
              </div>

              <div className="mt-1.5 flex items-center justify-between text-[9px] font-mono text-slate-400 pt-1 border-t border-white/[0.04]">
                <span>CONF: <strong className="text-emerald-300">{agent.confidencePct}%</strong></span>
                <span>ACCURACY: <strong className="text-slate-200">{agent.recentAccuracyPct}%</strong></span>
                <span className="text-emerald-400 uppercase">{agent.status}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Center: Central Synthesized Investment Thesis & Gated Consensus */}
        <div className="lg:col-span-4 flex flex-col items-center justify-center p-3 rounded-lg bg-black/50 border border-cyan-500/30 relative shadow-[0_0_20px_rgba(0,240,255,0.1)]">
          {/* Subtle pulsating radar ring */}
          <div className="w-10 h-10 rounded-full bg-cyan-500/10 border border-cyan-400/30 flex items-center justify-center mb-2 shadow-[0_0_12px_rgba(0,240,255,0.3)] animate-pulse-subtle">
            <Scale className="w-5 h-5 text-cyan-400" />
          </div>

          <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-400 font-bold text-center">
            ACTIVE INVESTMENT THESIS
          </div>

          <div className="text-sm font-semibold text-white text-center mt-1 px-2 leading-snug">
            Equities / Crypto Momentum Overweight with US 2Y/10Y Curve Steepener
          </div>

          <div className="w-full mt-3 pt-2 border-t border-white/[0.08] space-y-1.5 text-[10px] font-mono">
            <div className="flex justify-between text-slate-400">
              <span>CONSENSUS LEVEL:</span>
              <span className="text-cyan-300 font-bold font-mono-num">87.4% SUPERMAJORITY</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>OPPOSING CHALLENGES:</span>
              <span className="text-amber-400 font-medium">1 ADDRESSED</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>FIREWALL APPROVAL:</span>
              <span className="text-emerald-400 font-bold">15/15 CHECKS PASSED</span>
            </div>
          </div>

          {/* Gated Pipeline Stage Indicators */}
          <div className="mt-3 w-full grid grid-cols-4 gap-1 text-[8px] font-mono text-center">
            <div className="p-1 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800">
              1. INGEST
            </div>
            <div className="p-1 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800">
              2. DEBATE
            </div>
            <div className="p-1 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800">
              3. VERIFY
            </div>
            <div className="p-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-600 font-bold">
              4. GATED
            </div>
          </div>
        </div>

        {/* Right Column: Challenger & Verifier Agents */}
        <div className="lg:col-span-4 space-y-2">
          <div className="text-[10px] font-mono uppercase tracking-wider text-rose-400 font-semibold flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-ping"></span>
            CHALLENGER & FORMAL VERIFIERS
          </div>

          {[...bearAgents, ...neutralAgents.slice(0, 2)].map((agent) => (
            <div
              key={agent.id}
              onClick={() => onSelectAgent(agent)}
              onMouseEnter={() => setHoveredAgentId(agent.id)}
              onMouseLeave={() => setHoveredAgentId(null)}
              className={`p-2 rounded border transition-all cursor-pointer shadow-sm relative group ${
                agent.bias === 'BEAR'
                  ? 'bg-rose-950/20 hover:bg-rose-950/40 border-rose-800/40 hover:border-rose-500/60'
                  : 'bg-white/[0.02] hover:bg-white/[0.05] border-white/[0.06] hover:border-cyan-500/40'
              }`}
            >
              <div className="flex items-center justify-between text-xs font-mono">
                <span className={`font-bold ${agent.bias === 'BEAR' ? 'text-rose-300' : 'text-slate-200'} group-hover:text-white`}>
                  {agent.name}
                </span>
                <span className="text-[10px] px-1 rounded bg-black/40 text-slate-300 border border-white/[0.08] font-mono-num">
                  R: {agent.reputationScore.toFixed(2)}
                </span>
              </div>

              <div className="text-[10px] text-slate-300 mt-1 line-clamp-1 italic">
                "{agent.currentThesis}"
              </div>

              <div className="mt-1.5 flex items-center justify-between text-[9px] font-mono text-slate-400 pt-1 border-t border-white/[0.04]">
                <span>CONF: <strong className="text-cyan-300">{agent.confidencePct}%</strong></span>
                <span>LATENCY: <strong className="text-slate-300">{agent.latencyMs}ms</strong></span>
                <span className={agent.bias === 'BEAR' ? 'text-rose-400' : 'text-cyan-400'}>
                  {agent.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer Info */}
      <div className="pt-2 border-t border-white/[0.06] text-[10px] font-mono text-slate-500 flex items-center justify-between">
        <span>CONSTITUTION §3: MULTI-AGENT ADVERSARIAL DISCLOSURE</span>
        <span className="text-slate-400">Click any agent to inspect lineage & model weights</span>
      </div>
    </div>
  );
};
