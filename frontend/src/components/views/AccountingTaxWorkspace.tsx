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
 * badge comes from `balanced`. Controller sign-off has no server-side flow
 * (no matching control action), so it renders as an honest not-wired state
 * instead of a local attestation.
 */
export const AccountingTaxWorkspace: React.FC = () => {
  const accounting = useApi(() => riskApi.accounting());

  if (accounting.loading) {
    return <div className="text-xs text-text-muted font-mono p-8">Loading ledger from /api/v1/accounting…</div>;
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
      <span className="text-text-muted font-bold">UNKNOWN (backend did not report balance)</span>
    ) : adapted.balanced ? (
      <span className="text-positive font-bold">BALANCED (DEBITS = CREDITS)</span>
    ) : (
      <span className="text-destructive font-bold">OUT OF BALANCE — HALT AND INVESTIGATE</span>
    );

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ReceiptText className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              ACCOUNTING, TAX PROVISION & AUDITOR SIGN-OFF WORKSPACE
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
              FRAME 11
            </span>
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            Double-Entry Ledger • Source: /api/v1/accounting
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-surface-veil border border-border-subtle px-3 py-1.5 rounded">
            <span className="text-text-muted">TRIAL BALANCE:</span>{' '}
            {badge}
          </div>
          <div className="bg-surface-veil border border-border-subtle px-3 py-1.5 rounded">
            <span className="text-text-muted">TAX DUE:</span>{' '}
            <span className="text-accent font-bold">
              {adapted.taxDueMinor != null
                ? `$${(adapted.taxDueMinor / 100).toLocaleString()}`
                : "— (not computed)"}
            </span>
          </div>
        </div>
      </div>

      {/* Controller / Auditor Sign-Off Banner */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded flex items-center justify-center bg-surface-veil text-text-muted border border-border-strong">
            <FileCheck2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-bold text-text-strong flex items-center gap-2">
              <span>FUND CONTROLLER & STATUTORY COMPLIANCE OVERSIGHT</span>
              <span className="text-[9px] px-2 py-0.5 rounded font-bold bg-surface-veil text-text-muted border border-border-strong">
                SIGN-OFF NOT WIRED
              </span>
            </div>
            <div className="text-[11px] text-text-muted mt-0.5">
              No controller sign-off flow exists server-side (no matching control action)
              {adapted.requiresSignoff ? ' — professional sign-off is still required out of band' : ''}
            </div>
          </div>
        </div>

        <div>
          <span
            title="No server-side sign-off flow exists"
            className="px-4 py-2 rounded bg-surface-veil border border-border-strong text-text-subtle text-xs font-bold font-mono inline-flex items-center gap-2 cursor-not-allowed"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>SIGN-OFF NOT WIRED</span>
          </span>
        </div>
      </div>

      {/* General Ledger Table */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
          <div className="flex items-center gap-2">
            <Scale className="w-4 h-4 text-accent" />
            <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
              GENERAL LEDGER CHART OF ACCOUNTS & BALANCES
            </h3>
          </div>
          <span className="text-[10px] text-text-muted">SOURCE: accounts_minor (minor → USD)</span>
        </div>

        {adapted.rows.length === 0 ? (
          <div className="p-6 text-center text-text-subtle text-xs">
            Ledger returned no accounts. No postings have been recorded yet.
          </div>
        ) : (
          <div className="overflow-x-auto my-3">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border-subtle text-text-subtle text-[9px] uppercase tracking-wider">
                  <th className="py-2 px-2.5">ACCOUNT CODE</th>
                  <th className="py-2 px-2">ACCOUNT NAME</th>
                  <th className="py-2 px-2">TYPE</th>
                  <th className="py-2 px-2 text-right">BALANCE (USD)</th>
                  <th className="py-2 px-2 text-center">INTEGRITY</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-veil">
                {adapted.rows.map((acc) => (
                  <tr key={acc.code} className="hover:bg-surface-veil transition-colors">
                    <td className="py-2 px-2.5 font-bold text-accent">{acc.code}</td>
                    <td className="py-2 px-2 text-text-strong font-medium">{acc.name}</td>
                    <td className="py-2 px-2">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-veil text-text border border-border-subtle">
                        {acc.type}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-right font-mono-num font-bold text-text-strong">
                      ${acc.balanceUsd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-2 px-2 text-center">
                      <span className={`text-[9px] flex items-center justify-center gap-1 ${adapted.balanced ? 'text-positive' : 'text-text-subtle'}`}>
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
        <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
          <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider pb-2 border-b border-border-subtle">
            CA REVIEW QUEUE ({adapted.reviewQueue.length})
          </h3>
          <div className="mt-2 space-y-1.5 text-xs">
            {adapted.reviewQueue.map((r, i) => (
              <div key={i} className="flex items-center justify-between p-2 rounded bg-surface-veil border border-border-subtle">
                <span className="text-text-strong">{r.subject_ref ?? "—"}</span>
                <span className="text-[10px] text-warning">{r.state ?? "—"}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
