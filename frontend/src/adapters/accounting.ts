/**
 * accountingAdapter: /api/v1/accounting → ledger rows + trial-balance badge.
 *
 * Backend: { trial_balance_total, balanced, accounts_minor (code → minor),
 *            open_lot_qty, tax, ca_review_queue[] }
 * The ledger is the authority; balances are minor ints (cents) → USD.
 */
import { type Unavailable } from "./absent";

export interface LedgerRow {
  code: string;
  name: string;
  type: string;
  balanceUsd: number;
}

export interface AdaptedAccounting {
  rows: LedgerRow[];
  balanced: boolean | null;
  trialTotalMinor: number | null;
  taxDueMinor: number | null;
  requiresSignoff: boolean;
  reviewQueue: { subject_ref: string | null; state: string | null }[];
}

function accountType(code: string): string {
  if (code.startsWith("1")) return "ASSET";
  if (code.startsWith("2")) return "LIABILITY";
  if (code.startsWith("3")) return "EQUITY";
  if (code.startsWith("4")) return "REVENUE";
  if (code.startsWith("5")) return "EXPENSE";
  return "—";
}

interface AccountingPayload {
  trial_balance_total?: number | null;
  balanced?: boolean | null;
  accounts_minor?: Record<string, number>;
  open_lot_qty?: Record<string, number>;
  tax?: {
    tax_due_minor?: number | null;
    requires_signoff?: boolean;
  };
  ca_review_queue?: { subject_ref?: string | null; state?: string | null }[];
}

export function adaptAccounting(
  payload: AccountingPayload | { available: false; reason?: string },
): AdaptedAccounting | Unavailable {
  if ("available" in payload) {
    const reason = payload.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "accounting ledger unavailable" };
  }
  const accounts = payload.accounts_minor ?? {};
  const rows: LedgerRow[] = Object.entries(accounts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([code, minor]) => ({
      code,
      name: code,
      type: accountType(code),
      balanceUsd: minor / 100,
    }));
  return {
    rows,
    balanced: payload.balanced ?? null,
    trialTotalMinor: payload.trial_balance_total ?? null,
    taxDueMinor: payload.tax?.tax_due_minor ?? null,
    requiresSignoff: payload.tax?.requires_signoff ?? true,
    reviewQueue: (payload.ca_review_queue ?? []).map((r) => ({
      subject_ref: r.subject_ref ?? null,
      state: r.state ?? null,
    })),
  };
}
