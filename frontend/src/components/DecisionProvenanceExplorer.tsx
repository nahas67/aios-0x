import React, { useState } from 'react';
import { ProvenanceTrace } from '../types';
import { 
  Network, 
  ArrowDown, 
  ShieldCheck, 
  Hash, 
   
   
   
   
  
  Copy,
  Check
} from 'lucide-react';

interface DecisionProvenanceExplorerProps {
  traces: ProvenanceTrace[];
  selectedTraceId?: string;
  onSelectTrace?: (traceId: string) => void;
  className?: string;
}

export const DecisionProvenanceExplorer: React.FC<DecisionProvenanceExplorerProps> = ({
  traces,
  selectedTraceId,
  onSelectTrace,
  className = '',
}) => {
  const [currentId, setCurrentId] = useState<string>(selectedTraceId || traces[0]?.executionId || '');
  const [copiedHash, setCopiedHash] = useState<boolean>(false);
  const [expandedStep, setExpandedStep] = useState<string | null>('DECISION');

  const trace = traces.find(t => t.executionId === currentId) || traces[0];

  const handleCopyHash = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 1500);
  };

  if (!trace) return null;

  return (
    <div className={`bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header & Trade Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <Network className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-text-strong uppercase">
            DECISION PROVENANCE GRAPH & LINEAGE
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-positive-bg text-positive border border-positive flex items-center gap-1">
            <ShieldCheck className="w-3 h-3" />
            SHA-256 VERIFIED
          </span>
        </div>

        {/* Trade Switcher */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-text-subtle">TRACED EXECUTION:</span>
          <div className="flex items-center bg-surface-sunken p-0.5 rounded border border-border-strong">
            {traces.map(t => (
              <button
                key={t.executionId}
                onClick={() => {
                  setCurrentId(t.executionId);
                  if (onSelectTrace) onSelectTrace(t.executionId);
                }}
                className={`px-2.5 py-1 text-[11px] font-mono rounded transition-colors ${
                  trace.executionId === t.executionId
                    ? 'bg-info-bg text-accent border border-accent font-semibold shadow-sm'
                    : 'text-text-muted hover:text-text-strong'
                }`}
              >
                {t.symbol} ({t.side})
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Top Hash & Integrity Banner */}
      <div className="my-2.5 p-2 rounded bg-surface-sunken border border-border-subtle flex items-center justify-between text-xs font-mono">
        <div className="flex items-center gap-2 text-text-muted truncate">
          <Hash className="w-3.5 h-3.5 text-accent shrink-0" />
          <span className="text-text-subtle text-[10px]">INTEGRITY HASH:</span>
          <span className="text-text font-mono text-[11px] truncate select-all">
            {trace.integrityHash}
          </span>
        </div>
        <button
          onClick={() => handleCopyHash(trace.integrityHash)}
          className="text-text-muted hover:text-accent flex items-center gap-1 shrink-0 px-2 py-0.5 rounded bg-surface-veil text-[10px]"
        >
          {copiedHash ? <Check className="w-3 h-3 text-positive" /> : <Copy className="w-3 h-3" />}
          <span>{copiedHash ? 'COPIED' : 'COPY'}</span>
        </button>
      </div>

      {/* The 6-Stage Lineage Backward Graph */}
      <div className="space-y-2 py-2">
        {/* Step 1: EXECUTION */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'EXECUTION' ? null : 'EXECUTION')}
          className="p-3 rounded border bg-surface-veil border-border-subtle hover:border-accent cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-info-bg text-accent border border-accent font-mono text-[10px] flex items-center justify-center font-bold">
                1
              </span>
              <span className="font-mono text-accent font-bold uppercase tracking-wider text-[11px]">
                EXECUTION VENUE & FILL
              </span>
            </div>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span className="text-positive font-bold">{trace.side} {trace.quantity} {trace.symbol}</span>
              <span className="text-text-muted">@ ${trace.fillPrice.toLocaleString()}</span>
              <span className="text-text-subtle">Slippage: {trace.slippageBps} bps</span>
            </div>
          </div>

          {expandedStep === 'EXECUTION' && (
            <div className="mt-2.5 pt-2 border-t border-border-subtle grid grid-cols-3 gap-2 text-[10px] font-mono text-text-muted">
              <div>ORDER ID: <strong className="text-text-strong">{trace.executionId}</strong></div>
              <div>TIMESTAMP: <strong className="text-text-strong">{trace.timestamp}</strong></div>
              <div>ROUTING: <strong className="text-accent">TWAP SLICER (OPTIMAL)</strong></div>
            </div>
          )}
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-text-subtle">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 2: DECISION */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'DECISION' ? null : 'DECISION')}
          className="p-3 rounded border bg-info-bg border-accent hover:border-accent cursor-pointer transition-all shadow-[0_0_12px_rgba(0,240,255,0.06)]"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-info-bg text-accent border border-accent font-mono text-[10px] flex items-center justify-center font-bold">
                2
              </span>
              <span className="font-mono text-accent font-bold uppercase tracking-wider text-[11px]">
                AUTONOMOUS DECISION CONSENSUS
              </span>
            </div>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span className="text-accent font-semibold font-mono-num">
                Score: {(trace.decision.consensusScore * 100).toFixed(1)}%
              </span>
              <span className="text-positive flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-positive-bg border border-positive">
                <ShieldCheck className="w-3 h-3" /> FIREWALL PASSED
              </span>
            </div>
          </div>

          <div className="mt-2 text-[11px] text-text leading-relaxed font-sans pl-7">
            {trace.decision.rationale}
          </div>

          {expandedStep === 'DECISION' && (
            <div className="mt-2.5 pt-2 border-t border-border-subtle flex items-center justify-between text-[10px] font-mono text-text-muted pl-7">
              <div>DECISION AGENT: <span className="text-text-strong">{trace.decision.decisionAgent}</span></div>
              <div>FIREWALL DIGEST: <span className="text-text-muted truncate max-w-[200px]">{trace.decision.firewallDigest}</span></div>
            </div>
          )}
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-text-subtle">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 3: STRATEGY */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'STRATEGY' ? null : 'STRATEGY')}
          className="p-3 rounded border bg-surface-veil border-border-subtle hover:border-accent cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-violet text-violet border border-violet font-mono text-[10px] flex items-center justify-center font-bold">
                3
              </span>
              <span className="font-mono text-violet font-bold uppercase tracking-wider text-[11px]">
                INVESTMENT STRATEGY & RISK BUDGET
              </span>
            </div>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span className="text-text">{trace.strategy.name}</span>
              <span className="text-accent">Target Sharpe: {trace.strategy.targetSharpe}</span>
            </div>
          </div>

          {expandedStep === 'STRATEGY' && (
            <div className="mt-2.5 pt-2 border-t border-border-subtle grid grid-cols-3 gap-2 text-[10px] font-mono text-text-muted pl-7">
              <div>FAMILY: <strong className="text-text-strong">{trace.strategy.family}</strong></div>
              <div>ALLOCATED CAPITAL: <strong className="text-text-strong">${(trace.strategy.allocatedCapitalUsd / 1000000).toFixed(1)}M</strong></div>
              <div>STATUS: <strong className="text-positive">ACTIVE PRODUCTION</strong></div>
            </div>
          )}
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-text-subtle">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 4: HYPOTHESIS */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'HYPOTHESIS' ? null : 'HYPOTHESIS')}
          className="p-3 rounded border bg-surface-veil border-border-subtle hover:border-accent cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-violet text-violet border border-violet font-mono text-[10px] flex items-center justify-center font-bold">
                4
              </span>
              <span className="font-mono text-violet font-bold uppercase tracking-wider text-[11px]">
                FORMAL RESEARCH HYPOTHESIS
              </span>
            </div>
            <div className="flex items-center gap-2 font-mono text-[10px]">
              <span className="px-1.5 py-0.5 rounded bg-positive-bg text-positive border border-positive">
                {trace.hypothesis.verificationStatus}
              </span>
            </div>
          </div>

          <div className="mt-1.5 text-xs text-text-strong font-medium pl-7">
            {trace.hypothesis.title}
          </div>
          <div className="text-[11px] text-text-muted mt-1 pl-7 italic">
            "{trace.hypothesis.formalStatement}"
          </div>
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-text-subtle">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 5: EVIDENCE & ARGUMENTS */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'EVIDENCE' ? null : 'EVIDENCE')}
          className="p-3 rounded border bg-surface-veil border-border-subtle hover:border-accent cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-accent-info text-accent-info border border-accent-info font-mono text-[10px] flex items-center justify-center font-bold">
                5
              </span>
              <span className="font-mono text-accent-info font-bold uppercase tracking-wider text-[11px]">
                SUPPORTING & ADVERSARIAL EVIDENCE
              </span>
            </div>
            <span className="text-[10px] font-mono text-accent">
              Confidence: {(trace.evidence.confidence * 100).toFixed(1)}%
            </span>
          </div>

          <div className="mt-2 pl-7 space-y-1">
            <div className="text-[10px] font-mono text-positive font-semibold">SUPPORTING CLAIMS:</div>
            {trace.evidence.claims.map((claim, i) => (
              <div key={i} className="text-[11px] text-text flex items-start gap-1.5">
                <span className="text-positive">•</span>
                <span>{claim}</span>
              </div>
            ))}

            {trace.evidence.counterClaims.length > 0 && (
              <>
                <div className="text-[10px] font-mono text-destructive font-semibold mt-2">ADVERSARIAL COUNTER-ARGUMENTS:</div>
                {trace.evidence.counterClaims.map((claim, i) => (
                  <div key={i} className="text-[11px] text-text-muted flex items-start gap-1.5">
                    <span className="text-destructive">•</span>
                    <span>{claim}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-text-subtle">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 6: RAW SOURCE */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'SOURCE' ? null : 'SOURCE')}
          className="p-3 rounded border bg-surface-veil border-border-subtle hover:border-accent cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-surface-deep text-text border border-border-subtle font-mono text-[10px] flex items-center justify-center font-bold">
                6
              </span>
              <span className="font-mono text-text font-bold uppercase tracking-wider text-[11px]">
                INGESTION SOURCE & CRYPTOGRAPHIC FEED
              </span>
            </div>
            <span className="text-[10px] font-mono text-positive">
              SIGNATURE VERIFIED
            </span>
          </div>

          <div className="mt-2 pl-7 flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-text-muted">
            <div>FEED: <span className="text-accent">{trace.source.feed}</span></div>
            <div>RAW PAYLOAD HASH: <span className="text-text truncate max-w-[180px]">{trace.source.rawPayloadHash}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
};
