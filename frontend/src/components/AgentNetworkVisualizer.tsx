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
    <div className={`bg-[var(--color-surface-1)] border border-border-strong rounded-md p-3.5 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-text-strong uppercase">
            AI AGENT NETWORK & DEBATE TOPOLOGY
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
            LANGGRAPH GATED PIPELINE
          </span>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono">
          <span className="flex items-center gap-1 text-positive">
            <TrendingUp className="w-3 h-3" /> {bullAgents.length} BULL
          </span>
          <span className="flex items-center gap-1 text-destructive">
            <TrendingDown className="w-3 h-3" /> {bearAgents.length} BEAR
          </span>
          <span className="flex items-center gap-1 text-accent">
            <ShieldCheck className="w-3 h-3" /> {neutralAgents.length} NEUTRAL
          </span>
        </div>
      </div>

      {/* Main Multi-Agent Interactive Debate Field */}
      <div className="relative py-4 grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
        {/* Left Column: Bull Agents Cluster */}
        <div className="lg:col-span-4 space-y-2">
          <div className="text-[10px] font-mono uppercase tracking-wider text-positive font-semibold flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-positive animate-pulse"></span>
            BULLISH THESIS PROPOSERS
          </div>

          {bullAgents.map((agent) => (
            <div
              key={agent.id}
              onClick={() => onSelectAgent(agent)}
              onMouseEnter={() => setHoveredAgentId(agent.id)}
              onMouseLeave={() => setHoveredAgentId(null)}
              className="p-2 rounded bg-positive-bg hover:bg-positive-bg border border-positive hover:border-positive transition-all cursor-pointer shadow-sm relative group"
            >
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="font-bold text-positive group-hover:text-text-strong">
                  {agent.name}
                </span>
                <span className="text-[10px] px-1 rounded bg-positive-bg text-positive border border-positive font-mono-num">
                  R: {agent.reputationScore.toFixed(2)}
                </span>
              </div>

              <div className="text-[10px] text-text mt-1 line-clamp-1 italic">
                "{agent.currentThesis}"
              </div>

              <div className="mt-1.5 flex items-center justify-between text-[9px] font-mono text-text-muted pt-1 border-t border-border-subtle">
                <span>CONF: <strong className="text-positive">{agent.confidencePct}%</strong></span>
                <span>ACCURACY: <strong className="text-text-strong">{agent.recentAccuracyPct}%</strong></span>
                <span className="text-positive uppercase">{agent.status}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Center: Central Synthesized Investment Thesis & Gated Consensus */}
        <div className="lg:col-span-4 flex flex-col items-center justify-center p-3 rounded-lg bg-surface-deep border border-accent relative shadow-[0_0_20px_rgba(0,240,255,0.1)]">
          {/* Subtle pulsating radar ring */}
          <div className="w-10 h-10 rounded-full bg-accent border border-accent flex items-center justify-center mb-2 shadow-[0_0_12px_rgba(0,240,255,0.3)] animate-pulse-subtle">
            <Scale className="w-5 h-5 text-accent" />
          </div>

          <div className="text-[10px] font-mono uppercase tracking-widest text-accent font-bold text-center">
            ACTIVE INVESTMENT THESIS
          </div>

          <div className="text-sm font-semibold text-text-strong text-center mt-1 px-2 leading-snug">
            Agent roster topology ({agents.length} registered)
          </div>

          <div className="w-full mt-3 pt-2 border-t border-border-strong space-y-1.5 text-[10px] font-mono">
            <div className="flex justify-between text-text-muted">
              <span>ROSTER SIZE:</span>
              <span className="text-accent font-bold font-mono-num">{agents.length} AGENTS</span>
            </div>
            <div className="flex justify-between text-text-muted">
              <span>CONSENSUS LEVEL:</span>
              <span className="text-text-subtle font-mono-num">— (no debate feed here)</span>
            </div>
            <div className="flex justify-between text-text-muted">
              <span>FIREWALL APPROVAL:</span>
              <span className="text-text-subtle font-mono-num">— (see Risk tab)</span>
            </div>
          </div>

          {/* Gated Pipeline Stage Indicators */}
          <div className="mt-3 w-full grid grid-cols-4 gap-1 text-[8px] font-mono text-center">
            <div className="p-1 rounded bg-info-bg text-accent border border-accent">
              1. INGEST
            </div>
            <div className="p-1 rounded bg-info-bg text-accent border border-accent">
              2. DEBATE
            </div>
            <div className="p-1 rounded bg-info-bg text-accent border border-accent">
              3. VERIFY
            </div>
            <div className="p-1 rounded bg-positive-bg text-positive border border-positive font-bold">
              4. GATED
            </div>
          </div>
        </div>

        {/* Right Column: Challenger & Verifier Agents */}
        <div className="lg:col-span-4 space-y-2">
          <div className="text-[10px] font-mono uppercase tracking-wider text-destructive font-semibold flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-destructive animate-ping"></span>
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
                  ? 'bg-destructive-bg hover:bg-destructive-bg border-destructive hover:border-destructive'
                  : 'bg-surface-veil hover:bg-surface-raised border-border-subtle hover:border-accent'
              }`}
            >
              <div className="flex items-center justify-between text-xs font-mono">
                <span className={`font-bold ${agent.bias === 'BEAR' ? 'text-destructive' : 'text-text-strong'} group-hover:text-text-strong`}>
                  {agent.name}
                </span>
                <span className="text-[10px] px-1 rounded bg-surface-sunken text-text border border-border-strong font-mono-num">
                  R: {agent.reputationScore.toFixed(2)}
                </span>
              </div>

              <div className="text-[10px] text-text mt-1 line-clamp-1 italic">
                "{agent.currentThesis}"
              </div>

              <div className="mt-1.5 flex items-center justify-between text-[9px] font-mono text-text-muted pt-1 border-t border-border-subtle">
                <span>CONF: <strong className="text-accent">{agent.confidencePct}%</strong></span>
                <span>LATENCY: <strong className="text-text">{agent.latencyMs}ms</strong></span>
                <span className={agent.bias === 'BEAR' ? 'text-destructive' : 'text-accent'}>
                  {agent.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer Info */}
      <div className="pt-2 border-t border-border-subtle text-[10px] font-mono text-text-subtle flex items-center justify-between">
        <span>CONSTITUTION §3: MULTI-AGENT ADVERSARIAL DISCLOSURE</span>
        <span className="text-text-muted">Click any agent to inspect lineage & model weights</span>
      </div>
    </div>
  );
};
