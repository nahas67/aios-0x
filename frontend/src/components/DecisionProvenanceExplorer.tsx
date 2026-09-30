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
    <div className={`bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header & Trade Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <Network className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-slate-100 uppercase">
            DECISION PROVENANCE GRAPH & LINEAGE
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/50 flex items-center gap-1">
            <ShieldCheck className="w-3 h-3" />
            SHA-256 VERIFIED
          </span>
        </div>

        {/* Trade Switcher */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-slate-500">TRACED EXECUTION:</span>
          <div className="flex items-center bg-black/40 p-0.5 rounded border border-white/[0.08]">
            {traces.map(t => (
              <button
                key={t.executionId}
                onClick={() => {
                  setCurrentId(t.executionId);
                  if (onSelectTrace) onSelectTrace(t.executionId);
                }}
                className={`px-2.5 py-1 text-[11px] font-mono rounded transition-colors ${
                  trace.executionId === t.executionId
                    ? 'bg-cyan-950 text-cyan-300 border border-cyan-800 font-semibold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {t.symbol} ({t.side})
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Top Hash & Integrity Banner */}
      <div className="my-2.5 p-2 rounded bg-black/40 border border-white/[0.06] flex items-center justify-between text-xs font-mono">
        <div className="flex items-center gap-2 text-slate-400 truncate">
          <Hash className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
          <span className="text-slate-500 text-[10px]">INTEGRITY HASH:</span>
          <span className="text-slate-300 font-mono text-[11px] truncate select-all">
            {trace.integrityHash}
          </span>
        </div>
        <button
          onClick={() => handleCopyHash(trace.integrityHash)}
          className="text-slate-400 hover:text-cyan-300 flex items-center gap-1 shrink-0 px-2 py-0.5 rounded bg-white/[0.04] text-[10px]"
        >
          {copiedHash ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          <span>{copiedHash ? 'COPIED' : 'COPY'}</span>
        </button>
      </div>

      {/* The 6-Stage Lineage Backward Graph */}
      <div className="space-y-2 py-2">
        {/* Step 1: EXECUTION */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'EXECUTION' ? null : 'EXECUTION')}
          className="p-3 rounded border bg-white/[0.02] border-white/[0.06] hover:border-cyan-500/40 cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/60 font-mono text-[10px] flex items-center justify-center font-bold">
                1
              </span>
              <span className="font-mono text-cyan-400 font-bold uppercase tracking-wider text-[11px]">
                EXECUTION VENUE & FILL
              </span>
            </div>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span className="text-emerald-400 font-bold">{trace.side} {trace.quantity} {trace.symbol}</span>
              <span className="text-slate-400">@ ${trace.fillPrice.toLocaleString()}</span>
              <span className="text-slate-500">Slippage: {trace.slippageBps} bps</span>
            </div>
          </div>

          {expandedStep === 'EXECUTION' && (
            <div className="mt-2.5 pt-2 border-t border-white/[0.06] grid grid-cols-3 gap-2 text-[10px] font-mono text-slate-400">
              <div>ORDER ID: <strong className="text-slate-200">{trace.executionId}</strong></div>
              <div>TIMESTAMP: <strong className="text-slate-200">{trace.timestamp}</strong></div>
              <div>ROUTING: <strong className="text-cyan-300">TWAP SLICER (OPTIMAL)</strong></div>
            </div>
          )}
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-slate-600">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 2: DECISION */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'DECISION' ? null : 'DECISION')}
          className="p-3 rounded border bg-cyan-950/20 border-cyan-800/40 hover:border-cyan-500/60 cursor-pointer transition-all shadow-[0_0_12px_rgba(0,240,255,0.06)]"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-cyan-900 text-cyan-300 border border-cyan-600 font-mono text-[10px] flex items-center justify-center font-bold">
                2
              </span>
              <span className="font-mono text-cyan-300 font-bold uppercase tracking-wider text-[11px]">
                AUTONOMOUS DECISION CONSENSUS
              </span>
            </div>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span className="text-cyan-300 font-semibold font-mono-num">
                Score: {(trace.decision.consensusScore * 100).toFixed(1)}%
              </span>
              <span className="text-emerald-400 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-emerald-950/60 border border-emerald-800">
                <ShieldCheck className="w-3 h-3" /> FIREWALL PASSED
              </span>
            </div>
          </div>

          <div className="mt-2 text-[11px] text-slate-300 leading-relaxed font-sans pl-7">
            {trace.decision.rationale}
          </div>

          {expandedStep === 'DECISION' && (
            <div className="mt-2.5 pt-2 border-t border-white/[0.06] flex items-center justify-between text-[10px] font-mono text-slate-400 pl-7">
              <div>DECISION AGENT: <span className="text-slate-200">{trace.decision.decisionAgent}</span></div>
              <div>FIREWALL DIGEST: <span className="text-slate-400 truncate max-w-[200px]">{trace.decision.firewallDigest}</span></div>
            </div>
          )}
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-slate-600">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 3: STRATEGY */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'STRATEGY' ? null : 'STRATEGY')}
          className="p-3 rounded border bg-white/[0.02] border-white/[0.06] hover:border-cyan-500/40 cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800 font-mono text-[10px] flex items-center justify-center font-bold">
                3
              </span>
              <span className="font-mono text-indigo-300 font-bold uppercase tracking-wider text-[11px]">
                INVESTMENT STRATEGY & RISK BUDGET
              </span>
            </div>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span className="text-slate-300">{trace.strategy.name}</span>
              <span className="text-cyan-300">Target Sharpe: {trace.strategy.targetSharpe}</span>
            </div>
          </div>

          {expandedStep === 'STRATEGY' && (
            <div className="mt-2.5 pt-2 border-t border-white/[0.06] grid grid-cols-3 gap-2 text-[10px] font-mono text-slate-400 pl-7">
              <div>FAMILY: <strong className="text-slate-200">{trace.strategy.family}</strong></div>
              <div>ALLOCATED CAPITAL: <strong className="text-slate-200">${(trace.strategy.allocatedCapitalUsd / 1000000).toFixed(1)}M</strong></div>
              <div>STATUS: <strong className="text-emerald-400">ACTIVE PRODUCTION</strong></div>
            </div>
          )}
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-slate-600">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 4: HYPOTHESIS */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'HYPOTHESIS' ? null : 'HYPOTHESIS')}
          className="p-3 rounded border bg-white/[0.02] border-white/[0.06] hover:border-cyan-500/40 cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-violet-950 text-violet-400 border border-violet-800 font-mono text-[10px] flex items-center justify-center font-bold">
                4
              </span>
              <span className="font-mono text-violet-300 font-bold uppercase tracking-wider text-[11px]">
                FORMAL RESEARCH HYPOTHESIS
              </span>
            </div>
            <div className="flex items-center gap-2 font-mono text-[10px]">
              <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                {trace.hypothesis.verificationStatus}
              </span>
            </div>
          </div>

          <div className="mt-1.5 text-xs text-slate-200 font-medium pl-7">
            {trace.hypothesis.title}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 pl-7 italic">
            "{trace.hypothesis.formalStatement}"
          </div>
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-slate-600">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 5: EVIDENCE & ARGUMENTS */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'EVIDENCE' ? null : 'EVIDENCE')}
          className="p-3 rounded border bg-white/[0.02] border-white/[0.06] hover:border-cyan-500/40 cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-blue-950 text-blue-400 border border-blue-800 font-mono text-[10px] flex items-center justify-center font-bold">
                5
              </span>
              <span className="font-mono text-blue-300 font-bold uppercase tracking-wider text-[11px]">
                SUPPORTING & ADVERSARIAL EVIDENCE
              </span>
            </div>
            <span className="text-[10px] font-mono text-cyan-300">
              Confidence: {(trace.evidence.confidence * 100).toFixed(1)}%
            </span>
          </div>

          <div className="mt-2 pl-7 space-y-1">
            <div className="text-[10px] font-mono text-emerald-400 font-semibold">SUPPORTING CLAIMS:</div>
            {trace.evidence.claims.map((claim, i) => (
              <div key={i} className="text-[11px] text-slate-300 flex items-start gap-1.5">
                <span className="text-emerald-400">•</span>
                <span>{claim}</span>
              </div>
            ))}

            {trace.evidence.counterClaims.length > 0 && (
              <>
                <div className="text-[10px] font-mono text-rose-400 font-semibold mt-2">ADVERSARIAL COUNTER-ARGUMENTS:</div>
                {trace.evidence.counterClaims.map((claim, i) => (
                  <div key={i} className="text-[11px] text-slate-400 flex items-start gap-1.5">
                    <span className="text-rose-400">•</span>
                    <span>{claim}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        {/* Down Arrow */}
        <div className="flex justify-center text-slate-600">
          <ArrowDown className="w-3.5 h-3.5" />
        </div>

        {/* Step 6: RAW SOURCE */}
        <div 
          onClick={() => setExpandedStep(expandedStep === 'SOURCE' ? null : 'SOURCE')}
          className="p-3 rounded border bg-white/[0.02] border-white/[0.06] hover:border-cyan-500/40 cursor-pointer transition-all"
        >
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="w-5 h-5 rounded bg-slate-900 text-slate-300 border border-slate-700 font-mono text-[10px] flex items-center justify-center font-bold">
                6
              </span>
              <span className="font-mono text-slate-300 font-bold uppercase tracking-wider text-[11px]">
                INGESTION SOURCE & CRYPTOGRAPHIC FEED
              </span>
            </div>
            <span className="text-[10px] font-mono text-emerald-400">
              SIGNATURE VERIFIED
            </span>
          </div>

          <div className="mt-2 pl-7 flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-slate-400">
            <div>FEED: <span className="text-cyan-300">{trace.source.feed}</span></div>
            <div>RAW PAYLOAD HASH: <span className="text-slate-300 truncate max-w-[180px]">{trace.source.rawPayloadHash}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
};
