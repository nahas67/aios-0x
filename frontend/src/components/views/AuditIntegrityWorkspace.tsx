import React, { useState } from 'react';
import { 
  FileCheck2, 
  ShieldCheck, 
  Hash, 
  CheckCircle2, 
  Lock, 
   
  Activity, 
  
  Copy,
  Check
} from 'lucide-react';
import { mockAuditRecords, mockConstitution } from '../../data/mockData';
import { AuditRecord } from '../../types';

export const AuditIntegrityWorkspace: React.FC = () => {
  const [selectedRecord, setSelectedRecord] = useState<AuditRecord>(mockAuditRecords[0]);
  const [copiedHash, setCopiedHash] = useState<boolean>(false);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [verifiedSuccess, setVerifiedSuccess] = useState<boolean>(false);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 1500);
  };

  const handleVerifyChain = () => {
    setIsVerifying(true);
    setTimeout(() => {
      setIsVerifying(false);
      setVerifiedSuccess(true);
      setTimeout(() => setVerifiedSuccess(false), 4000);
    }, 1000);
  };

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <FileCheck2 className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              CRYPTOGRAPHIC AUDIT TRAIL & CONSTITUTIONAL INTEGRITY
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 12
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            SHA-256 Merkle Chain • Immutable Event Append Ledger • Autonomous Tamper Detection
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleVerifyChain}
            className="px-4 py-2 rounded bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-700/60 text-cyan-300 text-xs font-bold transition-all shadow-[0_0_12px_rgba(0,240,255,0.2)] flex items-center gap-2"
          >
            <ShieldCheck className={`w-4 h-4 ${isVerifying ? 'animate-spin' : ''}`} />
            <span>{isVerifying ? 'VERIFYING HASH TREE...' : 'RE-VERIFY ENTIRE MERKLE CHAIN'}</span>
          </button>
        </div>
      </div>

      {verifiedSuccess && (
        <div className="p-3 rounded bg-emerald-950/50 border border-emerald-700 text-emerald-300 text-xs flex items-center justify-between animate-fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Merkle Tree Root Hash Verified: All 4,829 blocks intact. Zero tamper signatures detected.</span>
          </div>
          <span className="text-[10px] font-mono">ROOT: 0x9b32e...</span>
        </div>
      )}

      {/* Merkle Chain Status Card */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase text-white tracking-wider">
              MERKLE CHAIN HEAD PINNED AT BLOCK #4,829
            </h3>
          </div>
          <span className="text-[10px] text-emerald-400 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            CHAIN UNBROKEN
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 my-3 text-xs">
          <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
            <div className="text-[9px] text-slate-500 uppercase">BLOCK HEIGHT</div>
            <div className="text-sm font-bold text-white mt-0.5">#4,829</div>
          </div>
          <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
            <div className="text-[9px] text-slate-500 uppercase">EVENTS RECORDED</div>
            <div className="text-sm font-bold text-cyan-300 mt-0.5">184,920 TOTAL</div>
          </div>
          <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
            <div className="text-[9px] text-slate-500 uppercase">TAMPER SIGNATURES</div>
            <div className="text-sm font-bold text-emerald-400 mt-0.5">0 DETECTED</div>
          </div>
          <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
            <div className="text-[9px] text-slate-500 uppercase">HASH ALGORITHM</div>
            <div className="text-sm font-bold text-slate-200 mt-0.5">SHA-256 (DOUBLE PIN)</div>
          </div>
        </div>
      </div>

      {/* Grid: Audit Log Table + Constitution Viewer */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* Audit Log Table */}
        <div className="xl:col-span-7 bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                CRYPTOGRAPHIC EVENT STREAM
              </h3>
            </div>
            <span className="text-[10px] text-slate-400">SELECT TO INSPECT RAW HASH</span>
          </div>

          <div className="space-y-2 my-3">
            {mockAuditRecords.map((rec) => {
              const isSelected = rec.id === selectedRecord.id;
              return (
                <div
                  key={rec.id}
                  onClick={() => setSelectedRecord(rec)}
                  className={`p-3 rounded border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-cyan-950/30 border-cyan-500/50 shadow-[0_0_12px_rgba(0,240,255,0.1)]'
                      : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04]'
                  }`}
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-[10px] font-bold text-cyan-400 uppercase">
                      BLOCK #{rec.blockHeight} • {rec.eventType}
                    </span>
                    <span className="text-[10px] text-slate-500">{rec.timestamp}</span>
                  </div>

                  <div className="text-xs text-slate-200 font-medium mt-1">
                    {rec.actionSummary}
                  </div>

                  <div className="mt-2 text-[10px] text-slate-500 flex items-center justify-between pt-1 border-t border-white/[0.04]">
                    <span>ACTOR: <strong className="text-slate-300">{rec.actor}</strong></span>
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" /> VERIFIED
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Record Raw Inspector + Constitution Viewer */}
        <div className="xl:col-span-5 space-y-4">
          {/* Selected Record Inspector */}
          <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <div className="text-[10px] text-cyan-400 uppercase font-bold tracking-widest">
                RAW RECORD INSPECTOR
              </div>
              <button
                onClick={() => handleCopy(JSON.stringify(selectedRecord.payload, null, 2))}
                className="text-[10px] text-slate-400 hover:text-white flex items-center gap-1 px-2 py-0.5 rounded bg-white/[0.04]"
              >
                {copiedHash ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                <span>{copiedHash ? 'COPIED' : 'COPY JSON'}</span>
              </button>
            </div>

            <div className="text-xs space-y-1.5">
              <div>PREVIOUS HASH: <span className="text-slate-400 text-[10px] block truncate">{selectedRecord.prevHash}</span></div>
              <div>CURRENT HASH: <span className="text-cyan-300 text-[10px] block truncate">{selectedRecord.currentHash}</span></div>
            </div>

            <div className="pt-2 border-t border-white/[0.06]">
              <div className="text-[10px] text-slate-500 mb-1 uppercase">RAW JSON PAYLOAD:</div>
              <pre className="p-2.5 rounded bg-black/60 border border-white/[0.05] text-[10px] text-slate-300 overflow-x-auto max-h-48 font-mono">
                {JSON.stringify(selectedRecord.payload, null, 2)}
              </pre>
            </div>
          </div>

          {/* Constitution v1.0.0 Viewer */}
          <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <Lock className="w-4 h-4 text-cyan-400" />
                <h4 className="text-xs font-bold uppercase text-white tracking-wider">
                  SYSTEM CONSTITUTION v1.0.0
                </h4>
              </div>
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                RATIFIED
              </span>
            </div>

            <div className="space-y-2 text-xs max-h-48 overflow-y-auto pr-1">
              {mockConstitution.rules.map((rule) => (
                <div key={rule.id} className="p-2 rounded bg-white/[0.02] border border-white/[0.05]">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-cyan-300 text-[11px]">{rule.id}</span>
                    <span className="text-[9px] px-1 rounded bg-black/40 text-emerald-400 border border-white/[0.08]">
                      {rule.enforcement}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-300 mt-1">{rule.statement}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
