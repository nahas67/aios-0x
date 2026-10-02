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
    <div className="fixed inset-0 z-50 overflow-hidden bg-surface-deep backdrop-blur-sm flex justify-end animate-fade-in">
      <div className="w-full max-w-xl bg-[var(--color-surface-1)] border-l border-border-strong h-full shadow-2xl flex flex-col justify-between p-6 font-mono overflow-y-auto">
        {/* Drawer Header */}
        <div>
          <div className="flex items-center justify-between pb-4 border-b border-border-strong">
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded bg-accent shadow-[0_0_8px_var(--color-accent)]"></div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-text-strong tracking-tight">{agent.name}</h2>
                  <span className="text-xs px-2 py-0.5 rounded bg-info-bg text-accent border border-accent font-semibold">
                    {agent.role}
                  </span>
                </div>
                <div className="text-xs text-text-muted mt-0.5">
                  MODEL: <strong className="text-text-strong">{agent.modelsUsed[0] ?? '—'}</strong>
                </div>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded bg-surface-veil hover:bg-surface-raised text-text-muted hover:text-text-strong transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Reputation & Confidence Banner */}
          <div className="grid grid-cols-2 gap-3 my-4">
            <div className="p-3 rounded bg-surface-veil border border-border-subtle">
              <div className="text-[10px] text-text-muted flex items-center gap-1">
                <Award className="w-3 h-3 text-accent" />
                REPUTATION SCORE
              </div>
              <div className="text-2xl font-mono-num font-bold text-text-strong mt-1">
                {agent.reputationScore.toFixed(2)} / 1.00
              </div>
              <div className="text-[10px] text-positive mt-0.5">TOP 5% IN MULTI-AGENT POOL</div>
            </div>

            <div className="p-3 rounded bg-surface-veil border border-border-subtle">
              <div className="text-[10px] text-text-muted">WIN RATE ACCURACY</div>
              <div className="text-2xl font-mono-num font-bold text-positive mt-1">
                {agent.recentAccuracyPct.toFixed(1)}%
              </div>
              <div className="text-[10px] text-text-muted mt-0.5">ROLLING 90-DAY WINDOW</div>
            </div>
          </div>

          {/* Current Thesis */}
          <div className="p-3.5 rounded bg-info-bg border border-accent space-y-2">
            <div className="text-[10px] text-accent uppercase tracking-widest font-bold">
              CURRENT FORMAL THESIS
            </div>
            <p className="text-sm text-text-strong leading-relaxed font-sans">
              "{agent.currentThesis}"
            </p>
            <div className="flex items-center justify-between text-xs pt-2 border-t border-border-subtle">
              <span className="text-text-muted">THESIS CONFIDENCE:</span>
              <span className="text-accent font-bold font-mono-num">{agent.confidencePct}%</span>
            </div>
          </div>

          {/* Governance & Specifications */}
          <div className="mt-4 p-3.5 rounded bg-surface-sunken border border-border-subtle space-y-2.5 text-xs">
            <div className="flex justify-between">
              <span className="text-text-muted">INFERENCE LATENCY:</span>
              <span className="text-text-strong font-mono-num">{agent.latencyMs} ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">CURRENT BIAS:</span>
              <span className={`font-semibold ${
                agent.bias === 'BULL' ? 'text-positive' : agent.bias === 'BEAR' ? 'text-destructive' : 'text-text'
              }`}>{agent.bias}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">STATUS:</span>
              <span className="text-positive font-medium uppercase">{agent.status}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">SYSTEM PROMPT PIN:</span>
              <span className="text-text-subtle">— (not published)</span>
            </div>
          </div>

          {/* Gated Consensus Thresholds */}
          <div className="mt-4 p-3 rounded bg-surface-veil border border-border-subtle space-y-2 text-xs">
            <div className="text-[10px] text-text-muted uppercase tracking-wider">
              CONSTITUTIONAL GATES
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-muted">Consensus Minimum:</span>
              <span className="text-text-subtle">— (see Settings)</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-muted">Adversarial Challenger Requirement:</span>
              <span className="text-text-subtle">— (see Settings)</span>
            </div>
          </div>
        </div>

        {/* Action Controls Footer */}
        <div className="mt-6 pt-4 border-t border-border-strong space-y-2">
          <div className="text-[10px] text-text-subtle uppercase tracking-wider mb-2">
            AGENT SUPERVISION
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => onAdjustWeight && onAdjustWeight(agent.id, 0.05)}
              className="py-2 px-3 rounded bg-surface-veil hover:bg-surface-raised border border-border-strong text-xs text-text-strong hover:text-text-strong transition-all font-semibold"
            >
              BOOST REPUTATION (+5%)
            </button>
            <button
              onClick={() => onAdjustWeight && onAdjustWeight(agent.id, -0.05)}
              className="py-2 px-3 rounded bg-surface-veil hover:bg-surface-raised border border-border-strong text-xs text-text-strong hover:text-text-strong transition-all font-semibold"
            >
              DAMPEN WEIGHT (-5%)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
