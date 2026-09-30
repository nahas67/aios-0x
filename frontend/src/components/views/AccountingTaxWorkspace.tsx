import React, { useState } from 'react';
import { 
  ReceiptText, 
   
  FileCheck2, 
   
  Scale, 
  CheckCircle2, 
   
  

} from 'lucide-react';

export const AccountingTaxWorkspace: React.FC = () => {
  const [controllerApproved, setControllerApproved] = useState<boolean>(false);
  const [approvalMessage, setApprovalMessage] = useState<string | null>(null);

  const handleControllerSignOff = () => {
    setControllerApproved(true);
    setApprovalMessage('Fund Controller & Compliance Auditor sign-off ratified. Financial ledger pinned to Merkle block #4830.');
  };

  const ledgerAccounts = [
    { code: '1010', name: 'USD Prime Brokerage Cash', type: 'ASSET', balance: 40220000 },
    { code: '1020', name: 'US Treasury Bills (3M)', type: 'ASSET', balance: 25000000 },
    { code: '1100', name: 'Digital Asset Inventory (Spot)', type: 'ASSET', balance: 34500000 },
    { code: '1200', name: 'Perpetual & Futures Margin Collateral', type: 'ASSET', balance: 44560000 },
    { code: '2010', name: 'Short Perpetual Swap Borrow Liabilities', type: 'LIABILITY', balance: 2200000 },
    { code: '3010', name: 'Partnership Equity Capital', type: 'EQUITY', balance: 135000000 },
    { code: '4010', name: 'Realized Trading P&L (YTD)', type: 'REVENUE', balance: 5250000 },
    { code: '4020', name: 'Funding Rate & Carry Yield', type: 'REVENUE', balance: 1830000 },
  ];

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
            Double-Entry Ledger • HIFO Tax Lot Sizing • Continuous Audit Trial Balance
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">TRIAL BALANCE:</span>{' '}
            <span className="text-emerald-400 font-bold">BALANCED (DEBITS = CREDITS)</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">UNREALIZED TAX RESERVE:</span>{' '}
            <span className="text-cyan-300 font-bold">$1,420,000 (EST.)</span>
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
                {controllerApproved ? 'RATIFIED & SIGNED' : 'PENDING DAILY SIGN-OFF'}
              </span>
            </div>
            <div className="text-[11px] text-slate-400 mt-0.5">
              Certified Statutory Accounting & Capital Integrity Attestation (Constitution §6)
            </div>
          </div>
        </div>

        <div>
          {controllerApproved ? (
            <div className="text-xs font-bold text-emerald-400 flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-950/60 border border-emerald-700">
              <CheckCircle2 className="w-4 h-4" />
              <span>CONTROLLER SIGN-OFF ATTESTED (#CTRL-2026-08)</span>
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
          <span className="text-[10px] text-slate-400">SIG: ed25519:59f1...489c</span>
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
          <span className="text-[10px] text-slate-400">GAAP & IFRS COMPLIANT</span>
        </div>

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
              {ledgerAccounts.map((acc) => (
                <tr key={acc.code} className="hover:bg-white/[0.02] transition-colors">
                  <td className="py-2 px-2.5 font-bold text-cyan-300">{acc.code}</td>
                  <td className="py-2 px-2 text-white font-medium">{acc.name}</td>
                  <td className="py-2 px-2">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-300 border border-white/[0.06]">
                      {acc.type}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right font-mono-num font-bold text-slate-100">
                    ${acc.balance.toLocaleString()}
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className="text-[9px] text-emerald-400 flex items-center justify-center gap-1">
                      <CheckCircle2 className="w-3 h-3" /> VERIFIED
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
