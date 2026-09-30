import React, { useState } from 'react';
import {
  FileCheck2,
  ShieldCheck,
  Hash,
  CheckCircle2,
  Activity,
  Copy,
  Check
} from 'lucide-react';
import { auditApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { adaptAudit } from '../../adapters/audit';
import { Unavailable } from '../Unavailable';
import { AuditRecord } from '../../types';

/**
 * Audit workspace wired to GET /api/v1/audit + /api/v1/audit/verify.
 * The verify button walks the real hash chain server-side; every number
 * (blocks checked, head hash, breaks) is recomputed per call.
 */
export const AuditIntegrityWorkspace: React.FC = () => {
  const auditQ = useApi(() => auditApi.audit("", 50));
  const [verifyTick, setVerifyTick] = useState(0);
  const verifyQ = useApi(() => auditApi.verify(), [verifyTick]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<boolean>(false);

  if (auditQ.loading) {
    return <div className="text-xs text-slate-400 font-mono p-8">Loading audit log from /api/v1/audit…</div>;
  }
  if (auditQ.error || !auditQ.data) {
    return <Unavailable title="Audit unavailable" reason={auditQ.error ?? "no audit payload"} />;
  }
  const adapted = adaptAudit(auditQ.data);
  if ("unavailable" in adapted) {
    return <Unavailable title="Audit unavailable" reason={adapted.unavailable} />;
  }
  const records: AuditRecord[] = adapted;
  const selectedRecord = records.find((r) => r.id === selectedId) ?? records[0] ?? null;

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(true);
    setTimeout(() => setCopiedHash(false), 1500);
  };

  const verify = verifyQ.data;

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
            {records.length} records (latest 50) • Source: /api/v1/audit • Verify: /api/v1/audit/verify
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setVerifyTick((t) => t + 1)}
            className="px-4 py-2 rounded bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-700/60 text-cyan-300 text-xs font-bold transition-all shadow-[0_0_12px_rgba(0,240,255,0.2)] flex items-center gap-2"
          >
            <ShieldCheck className={`w-4 h-4 ${verifyQ.loading ? 'animate-spin' : ''}`} />
            <span>{verifyQ.loading ? 'VERIFYING HASH CHAIN…' : 'RE-VERIFY ENTIRE HASH CHAIN'}</span>
          </button>
        </div>
      </div>

      {verifyQ.error && (
        <Unavailable title="Chain verification failed" reason={verifyQ.error} />
      )}
      {verify && (
        <div className={`p-3 rounded border text-xs flex items-center justify-between animate-fade-in ${verify.valid ? 'bg-emerald-950/50 border-emerald-700 text-emerald-300' : 'bg-rose-950/50 border-rose-700 text-rose-300'}`}>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            <span>
              {verify.valid
                ? `Hash chain valid: ${verify.blocks_checked} blocks checked, zero breaks.`
                : `CHAIN BROKEN: ${verify.breaks.length} break(s) in ${verify.blocks_checked} blocks.`}
            </span>
          </div>
          <span className="text-[10px] font-mono">HEAD: {verify.head_hash.slice(0, 10)}…</span>
        </div>
      )}

      {/* Chain Status Card */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Hash className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase text-white tracking-wider">
              HASH CHAIN STATUS (SERVER-VERIFIED)
            </h3>
          </div>
          <span className={`text-[10px] flex items-center gap-1 ${verify?.valid ? 'text-emerald-400' : 'text-slate-400'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${verify?.valid ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`}></span>
            {verify ? (verify.valid ? "CHAIN UNBROKEN" : "CHAIN BROKEN") : "NOT YET VERIFIED — PRESS RE-VERIFY"}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 my-3 text-xs">
          <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
            <div className="text-[9px] text-slate-500 uppercase">BLOCKS CHECKED</div>
            <div className="text-sm font-bold text-white mt-0.5">{verify ? verify.blocks_checked.toLocaleString() : "—"}</div>
          </div>
          <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
            <div className="text-[9px] text-slate-500 uppercase">RECORDS SHOWN</div>
            <div className="text-sm font-bold text-cyan-300 mt-0.5">{records.length} TOTAL</div>
          </div>
          <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
            <div className="text-[9px] text-slate-500 uppercase">CHAIN BREAKS</div>
            <div className={`text-sm font-bold mt-0.5 ${verify && !verify.valid ? 'text-rose-400' : 'text-emerald-400'}`}>
              {verify ? `${verify.breaks.length} DETECTED` : "—"}
            </div>
          </div>
          <div className="p-2.5 rounded bg-black/40 border border-white/[0.05]">
            <div className="text-[9px] text-slate-500 uppercase">HASH ALGORITHM</div>
            <div className="text-sm font-bold text-slate-200 mt-0.5">SHA-256</div>
          </div>
        </div>
      </div>

      {/* Grid: Audit Log Table + Raw Inspector */}
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
            {records.length === 0 && (
              <div className="p-6 text-center text-slate-500 text-xs">
                Event log is empty. Nothing has been recorded yet.
              </div>
            )}
            {records.map((rec) => {
              const isSelected = rec.id === selectedRecord?.id;
              return (
                <div
                  key={rec.id}
                  onClick={() => setSelectedId(rec.id ?? null)}
                  className={`p-3 rounded border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-cyan-950/30 border-cyan-500/50 shadow-[0_0_12px_rgba(0,240,255,0.1)]'
                      : 'bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.04]'
                  }`}
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-[10px] font-bold text-cyan-400 uppercase">
                      SEQ #{rec.seq} • {rec.eventType}
                    </span>
                    <span className="text-[10px] text-slate-500">{rec.timestamp}</span>
                  </div>

                  <div className="text-xs text-slate-200 font-medium mt-1">
                    {rec.actionSummary}
                  </div>

                  <div className="mt-2 text-[10px] text-slate-500 flex items-center justify-between pt-1 border-t border-white/[0.04]">
                    <span>ACTOR: <strong className="text-slate-300">{rec.actor}</strong></span>
                    <span className="text-slate-500">
                      PER-ROW PROOF: NOT PUBLISHED
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Record Raw Inspector */}
        <div className="xl:col-span-5 space-y-4">
          <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <div className="text-[10px] text-cyan-400 uppercase font-bold tracking-widest">
                RAW RECORD INSPECTOR
              </div>
              <button
                onClick={() => selectedRecord && handleCopy(JSON.stringify(selectedRecord.payload, null, 2))}
                className="text-[10px] text-slate-400 hover:text-white flex items-center gap-1 px-2 py-0.5 rounded bg-white/[0.04]"
              >
                {copiedHash ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                <span>{copiedHash ? 'COPIED' : 'COPY JSON'}</span>
              </button>
            </div>

            {selectedRecord ? (
              <>
                <div className="text-xs space-y-1.5">
                  <div>SEQ: <span className="text-cyan-300 text-[11px]">{selectedRecord.seq}</span></div>
                  <div>REF: <span className="text-slate-400 text-[11px]">{selectedRecord.refId ?? "—"}</span></div>
                </div>

                <div className="pt-2 border-t border-white/[0.06]">
                  <div className="text-[10px] text-slate-500 mb-1 uppercase">RAW JSON PAYLOAD:</div>
                  <pre className="p-2.5 rounded bg-black/60 border border-white/[0.05] text-[10px] text-slate-300 overflow-x-auto max-h-48 font-mono">
                    {JSON.stringify(selectedRecord.payload, null, 2)}
                  </pre>
                </div>
              </>
            ) : (
              <div className="text-xs text-slate-500">No record selected.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
