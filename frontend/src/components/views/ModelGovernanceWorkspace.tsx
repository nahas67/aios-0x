import React, { useState } from 'react';
import { 
  Binary, 
  ShieldCheck, 
   
  CheckCircle2, 
   
   
   
   
  

} from 'lucide-react';

export const ModelGovernanceWorkspace: React.FC = () => {
  const [selectedModel, setSelectedModel] = useState<string>('MOD-01');

  const lifecycleStages = [
    { name: '1. INIT', desc: 'Dataset curation & clean' },
    { name: '2. TRAIN', desc: 'Pretrain / LoRA adapt' },
    { name: '3. EVALUATE', desc: 'Purged backtesting' },
    { name: '4. PROMOTE', desc: 'Formal gate approval' },
    { name: '5. DEPLOY', desc: 'Sandboxed canary' },
    { name: '6. MONITOR', desc: 'Drift & latency watch' },
    { name: '7. REPUTATION', desc: 'Dynamic score adjust' },
    { name: '8. RETIRE', desc: 'Deprecated archive' },
  ];

  const models = [
    {
      id: 'MOD-01',
      name: 'AIOS-DeepSeek-R1-Finance-671B',
      stage: 'DEPLOY',
      domain: 'Macro Reasoning & Deep Math',
      weightsHash: 'sha256:7f83b165...904b',
      accuracyPct: 91.2,
      latencyMs: 380,
      contextLength: '128k tokens',
      lastEvaluated: '2026-08-30',
      status: 'PRODUCTION_CANARY',
    },
    {
      id: 'MOD-02',
      name: 'AIOS-Claude-3.5-Sonnet-Quant',
      stage: 'MONITOR',
      domain: 'Hypothesis Synthesis & Verification',
      weightsHash: 'sha256:3a19e48c...8b77',
      accuracyPct: 94.8,
      latencyMs: 145,
      contextLength: '200k tokens',
      lastEvaluated: '2026-08-31',
      status: 'PRODUCTION_ACTIVE',
    },
    {
      id: 'MOD-03',
      name: 'AIOS-Qwen-2.5-72B-Perps-LoRA',
      stage: 'EVALUATE',
      domain: 'High-Frequency Perp Microstructure',
      weightsHash: 'sha256:c92e105d...110a',
      accuracyPct: 86.4,
      latencyMs: 42,
      contextLength: '32k tokens',
      lastEvaluated: '2026-08-28',
      status: 'EVALUATION_PASS',
    },
    {
      id: 'MOD-04',
      name: 'AIOS-GPT-4o-Sentinel-v2',
      stage: 'MONITOR',
      domain: 'Regulatory & Constitution Sieve',
      weightsHash: 'sha256:b174ac90...fa31',
      accuracyPct: 98.1,
      latencyMs: 110,
      contextLength: '128k tokens',
      lastEvaluated: '2026-08-31',
      status: 'PRODUCTION_ACTIVE',
    },
  ];

  const activeModel = models.find(m => m.id === selectedModel) || models[0];

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Binary className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              MODEL GOVERNANCE & 8-STAGE LIFECYCLE PIPELINE
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 10
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            MLflow Registry • Model Weights Provenance • Non-repudiable Checkpoint Hashing
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">ACTIVE PRODUCTION MODELS:</span>{' '}
            <span className="text-emerald-400 font-bold">4 INFERENCE ENGINES</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">BENCHMARK ACCURACY:</span>{' '}
            <span className="text-cyan-300 font-bold">92.6% AVERAGE</span>
          </div>
        </div>
      </div>

      {/* The 8-Stage Model Lifecycle Visual Progress Ribbon */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold mb-3">
          8-STAGE DETERMINISTIC MODEL LIFECYCLE
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {lifecycleStages.map((stg) => (
            <div 
              key={stg.name}
              className="p-2 rounded bg-white/[0.02] border border-white/[0.06] text-center flex flex-col justify-between"
            >
              <div className="text-[10px] font-bold text-slate-200">{stg.name}</div>
              <div className="text-[9px] text-slate-400 mt-1 leading-tight">{stg.desc}</div>
              <div className="mt-2 text-[8px] text-emerald-400 flex items-center justify-center gap-1 font-semibold">
                <CheckCircle2 className="w-2.5 h-2.5" /> PASSED
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Model Registry Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* Left: Model List */}
        <div className="xl:col-span-6 space-y-3">
          <div className="text-[10px] uppercase text-slate-400 font-bold tracking-wider">
            REGISTERED PRODUCTION MODELS
          </div>

          {models.map((mod) => {
            const isSelected = mod.id === selectedModel;
            return (
              <div
                key={mod.id}
                onClick={() => setSelectedModel(mod.id)}
                className={`p-3.5 rounded border transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-cyan-950/30 border-cyan-500/50 shadow-[0_0_15px_rgba(0,240,255,0.1)]'
                    : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04]'
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <div className="font-bold text-white flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                    <span>{mod.name}</span>
                  </div>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                    STAGE: {mod.stage}
                  </span>
                </div>

                <div className="text-[11px] text-slate-400 mt-1">
                  Domain: {mod.domain}
                </div>

                <div className="mt-2.5 pt-2 border-t border-white/[0.04] grid grid-cols-3 gap-2 text-[10px]">
                  <div>ACCURACY: <strong className="text-emerald-400">{mod.accuracyPct}%</strong></div>
                  <div>LATENCY: <strong className="text-slate-200">{mod.latencyMs}ms</strong></div>
                  <div>CONTEXT: <strong className="text-cyan-300">{mod.contextLength}</strong></div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: Model Deep Metadata Inspector */}
        <div className="xl:col-span-6 bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
            <div>
              <div className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold">
                WEIGHTS PROVENANCE & RUNTIME SPECS
              </div>
              <h3 className="text-base font-bold text-white mt-0.5">{activeModel.name}</h3>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">
              {activeModel.status}
            </span>
          </div>

          <div className="space-y-2 text-xs">
            <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between">
              <span className="text-slate-400">IMMUTABLE WEIGHTS HASH:</span>
              <span className="text-cyan-300 font-mono select-all text-[11px]">{activeModel.weightsHash}</span>
            </div>
            <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between">
              <span className="text-slate-400">INFERENCE LATENCY:</span>
              <span className="text-white font-mono-num font-bold">{activeModel.latencyMs} ms (P99)</span>
            </div>
            <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between">
              <span className="text-slate-400">OUT-OF-SAMPLE WIN RATE:</span>
              <span className="text-emerald-400 font-mono-num font-bold">{activeModel.accuracyPct}%</span>
            </div>
            <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between">
              <span className="text-slate-400">SYSTEM PROMPT HASH:</span>
              <span className="text-slate-300 font-mono text-[11px]">sha256:d824...fa01</span>
            </div>
            <div className="p-2 rounded bg-black/40 border border-white/[0.05] flex justify-between">
              <span className="text-slate-400">TEMPERATURE / SAMPLING:</span>
              <span className="text-slate-200">T=0.10 (Deterministic Greedy)</span>
            </div>
          </div>

          <div className="p-3 rounded bg-emerald-950/20 border border-emerald-800/40 text-xs text-emerald-300 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>Cryptographically certified for institutional execution governance (§4.1 ratified)</span>
          </div>
        </div>
      </div>
    </div>
  );
};
