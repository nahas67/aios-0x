import React from 'react';
import {
  ReceiptText,
  FileCheck2,
  Scale,
  CheckCircle2,
} from 'lucide-react';
import { riskApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { adaptAccounting } from '../../adapters/accounting';
import { Unavailable } from '../Unavailable';

/**
 * Accounting workspace wired to GET /api/v1/accounting.
 * Ledger rows come from accounts_minor (minor → USD); the TRIAL BALANCE
 * badge comes from `balanced`. The controller sign-off is a local UI
 * attestation only — it anchors nothing until a server-side flow exists.
 */
export const AccountingTaxWorkspace: React.FC = () => {
  const [controllerApproved, setControllerApproved] = React.useState<boolean>(false);
  const [approvalMessage, setApprovalMessage] = React.useState<string | null>(null);
  const accounting = useApi(() => riskApi.accounting());

  const handleControllerSignOff = () => {
    setControllerApproved(true);
    setApprovalMessage('Fund Controller sign-off recorded locally (not anchored to any Merkle block).');
  };

  if (accounting.loading) {
    return <div className="text-xs text-slate-400 font-mono p-8">Loading ledger from /api/v1/accounting…</div>;
  }
  if (accounting.error || !accounting.data) {
    return <Unavailable title="Accounting unavailable" reason={accounting.error ?? "no ledger payload"} />;
  }

  const adapted = adaptAccounting(accounting.data);
  if ("unavailable" in adapted) {
    return <Unavailable title="Accounting unavailable" reason={adapted.unavailable} />;
  }

  const badge =
    adapted.balanced == null ? (
      <span className="text-slate-400 font-bold">UNKNOWN (backend did not report balance)</span>
    ) : adapted.balanced ? (
      <span className="text-emerald-400 font-bold">BALANCED (DEBITS = CREDITS)</span>
    ) : (
      <span className="text-rose-400 font-bold">OUT OF BALANCE — HALT AND INVESTIGATE</span>
    );

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ReceiptText className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              ACCOUNTING, TAX PROVISION & AUDITOR SIGN-OFF WORKSPACE
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 11
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Double-Entry Ledger • Source: /api/v1/accounting
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">TRIAL BALANCE:</span>{' '}
            {badge}
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">TAX DUE:</span>{' '}
            <span className="text-cyan-300 font-bold">
              {adapted.taxDueMinor != null
                ? `$${(adapted.taxDueMinor / 100).toLocaleString()}`
                : "— (not computed)"}
            </span>
          </div>
        </div>
      </div>

      {/* Controller / Auditor Sign-Off Banner */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded flex items-center justify-center ${
            controllerApproved ? 'bg-emerald-950 text-emerald-400 border border-emerald-700' : 'bg-indigo-950 text-indigo-400 border border-indigo-700'
          }`}>
            <FileCheck2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-bold text-white flex items-center gap-2">
              <span>FUND CONTROLLER & STATUTORY COMPLIANCE OVERSIGHT</span>
              <span className={`text-[9px] px-2 py-0.5 rounded font-bold ${
                controllerApproved ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-amber-950 text-amber-300 border border-amber-800'
              }`}>
                {controllerApproved ? 'RECORDED LOCALLY' : 'PENDING DAILY SIGN-OFF'}
              </span>
            </div>
            <div className="text-[11px] text-slate-400 mt-0.5">
              Local attestation only — no server-side sign-off flow exists yet
              {adapted.requiresSignoff ? ' (professional sign-off required)' : ''}
            </div>
          </div>
        </div>

        <div>
          {controllerApproved ? (
            <div className="text-xs font-bold text-emerald-400 flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-950/60 border border-emerald-700">
              <CheckCircle2 className="w-4 h-4" />
              <span>CONTROLLER SIGN-OFF RECORDED</span>
            </div>
          ) : (
            <button
              onClick={handleControllerSignOff}
              className="px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold font-mono transition-all shadow-[0_0_12px_rgba(99,102,241,0.4)] flex items-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>RATIFY DAILY CONTROLLER SIGN-OFF</span>
            </button>
          )}
        </div>
      </div>

      {approvalMessage && (
        <div className="p-3 rounded bg-emerald-950/50 border border-emerald-700 text-emerald-300 text-xs flex items-center justify-between animate-fade-in">
          <span>{approvalMessage}</span>
        </div>
      )}

      {/* General Ledger Table */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Scale className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase text-white tracking-wider">
              GENERAL LEDGER CHART OF ACCOUNTS & BALANCES
            </h3>
          </div>
          <span className="text-[10px] text-slate-400">SOURCE: accounts_minor (minor → USD)</span>
        </div>

        {adapted.rows.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-xs">
            Ledger returned no accounts. No postings have been recorded yet.
          </div>
        ) : (
          <div className="overflow-x-auto my-3">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-white/[0.06] text-slate-500 text-[9px] uppercase tracking-wider">
                  <th className="py-2 px-2.5">ACCOUNT CODE</th>
                  <th className="py-2 px-2">ACCOUNT NAME</th>
                  <th className="py-2 px-2">TYPE</th>
                  <th className="py-2 px-2 text-right">BALANCE (USD)</th>
                  <th className="py-2 px-2 text-center">INTEGRITY</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.03]">
                {adapted.rows.map((acc) => (
                  <tr key={acc.code} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-2 px-2.5 font-bold text-cyan-300">{acc.code}</td>
                    <td className="py-2 px-2 text-white font-medium">{acc.name}</td>
                    <td className="py-2 px-2">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-300 border border-white/[0.06]">
                        {acc.type}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-right font-mono-num font-bold text-slate-100">
                      ${acc.balanceUsd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-2 px-2 text-center">
                      <span className={`text-[9px] flex items-center justify-center gap-1 ${adapted.balanced ? 'text-emerald-400' : 'text-slate-500'}`}>
                        <CheckCircle2 className="w-3 h-3" /> {adapted.balanced ? 'VERIFIED' : '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* CA review queue */}
      {adapted.reviewQueue.length > 0 && (
        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
          <h3 className="text-xs font-bold uppercase text-white tracking-wider pb-2 border-b border-white/[0.06]">
            CA REVIEW QUEUE ({adapted.reviewQueue.length})
          </h3>
          <div className="mt-2 space-y-1.5 text-xs">
            {adapted.reviewQueue.map((r, i) => (
              <div key={i} className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/[0.05]">
                <span className="text-slate-200">{r.subject_ref ?? "—"}</span>
                <span className="text-[10px] text-amber-300">{r.state ?? "—"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
