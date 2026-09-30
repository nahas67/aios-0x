import React from 'react';
import { Unavailable } from '../Unavailable';

/**
 * Financial Kernel workspace (stub). The durable book of record behind
 * /api/v1/financial/* is fully backed, but its adapters have not landed yet
 * (plan step 4). Until every number on screen is traceable to an endpoint,
 * this tab honestly reports absence instead of rendering the old mock book.
 */
export const FinancialKernelWorkspace: React.FC = () => {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold text-slate-100">Financial Kernel</h1>
        <p className="text-xs text-slate-400">Durable book of record — IBOR, cash, orders, fills, invariants</p>
      </div>
      <Unavailable
        title="Financial Kernel — not yet wired"
        reason="Adapters from /api/v1/financial/* (ibor, positions, cash, orders, fills, invariants, health, outbox, reconciliation) have not landed yet. This workspace stays empty rather than showing data that cannot be traced to the backend."
      />
    </div>
  );
};
