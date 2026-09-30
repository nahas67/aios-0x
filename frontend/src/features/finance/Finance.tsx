import { portfolioApi, riskApi } from "../../api/endpoints";
import { BarChart } from "../../components/charts";
import { DataTable, Empty, ErrorBox, KV, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtNum, fmtPct, fmtSigned, fmtUsd, pnlClass, statusTone } from "../../lib/format";

export function PnlPage() {
  const pnl = useApi(() => portfolioApi.pnl());
  const strategies = useApi(() => portfolioApi.strategies());
  const p = pnl.data;

  if (pnl.error) return <ErrorBox title="P&L unavailable" detail={pnl.error} />;

  return (
    <>
      <div className="pagehead">
        <h1>P&L</h1>
        <span className="sub">Realized performance by strategy family and symbol — engine-computed</span>
      </div>
      <div className="grid cols-4" style={{ marginBottom: "var(--gap)" }}>
        <Panel>
          <div className={`big-num ${pnlClass(p?.totals.pnl ?? null)}`}>{fmtSigned(p?.totals.pnl ?? null, fmtUsd)}</div>
          <div className="dim" style={{ fontSize: 11 }}>cumulative realized</div>
        </Panel>
        <Panel>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{fmtNum(p?.totals.trades ?? 0)}</div>
          <div className="dim" style={{ fontSize: 11 }}>closed trades</div>
        </Panel>
        <Panel>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{fmtPct(p?.totals.win_rate_pct ?? null)}</div>
          <div className="dim" style={{ fontSize: 11 }}>win rate</div>
        </Panel>
        <Panel>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{fmtUsd(p?.totals.fees ?? null)}</div>
          <div className="dim" style={{ fontSize: 11 }}>fees paid</div>
        </Panel>
      </div>
      <div className="grid cols-2">
        <Panel title="P&L by Strategy Family">
          <BarChart
            entries={Object.entries(p?.by_family ?? {}).map(([label, b]) => ({ label, value: b.pnl }))}
            formatValue={(v) => fmtSigned(v, (n) => `$${Math.abs(n).toFixed(0)}`)}
          />
        </Panel>
        <Panel title="P&L by Symbol">
          <BarChart
            entries={Object.entries(p?.by_symbol ?? {}).map(([label, b]) => ({ label, value: b.pnl }))}
            formatValue={(v) => fmtSigned(v, (n) => `$${Math.abs(n).toFixed(0)}`)}
          />
        </Panel>
      </div>
      <div style={{ marginTop: "var(--gap)" }}>
        <Panel title="Strategy Performance">
          <DataTable
            rows={strategies.data?.strategies}
            rowKey={(s) => s.family}
            empty="No strategy stats yet."
            columns={[
              { key: "family", label: "Family", render: (s) => <span className="sym">{s.family}</span> },
              { key: "trades", label: "Trades", numeric: true },
              { key: "wins", label: "Wins", numeric: true },
              { key: "losses", label: "Losses", numeric: true },
              { key: "win_rate_pct", label: "Win rate", numeric: true, render: (s) => fmtPct(s.win_rate_pct) },
              { key: "pnl", label: "P&L", numeric: true, render: (s) => <span className={pnlClass(s.pnl)}>{fmtSigned(s.pnl, fmtUsd)}</span> },
              { key: "active", label: "Active", render: (s) => <Pill tone={s.active ? "ok" : "dim"}>{s.active ? "ACTIVE" : "OFF"}</Pill> },
            ]}
          />
        </Panel>
      </div>
    </>
  );
}

interface Accounting {
  trial_balance_total: number | null;
  balanced: boolean | null;
  accounts_minor: Record<string, number> | null;
  open_lot_qty: Record<string, number> | null;
  tax: {
    rule_citation: string | null;
    jurisdiction: string | null;
    taxable_gain_minor: number | null;
    tax_due_minor: number | null;
    requires_signoff: boolean;
    ca_state: string | null;
  };
  ca_review_queue: { subject_ref: string; state: string }[];
}

export function AccountingPage() {
  const acct = useApi(() => riskApi.accounting());
  const a = acct.data as Accounting | null;

  if (acct.error) return <ErrorBox title="Accounting unavailable" detail={acct.error} />;

  return (
    <>
      <div className="pagehead">
        <h1>Accounting</h1>
        <span className="sub">Double-entry ledger integrity — trial balance must sum to zero</span>
      </div>
      <div className="grid cols-3" style={{ marginBottom: "var(--gap)" }}>
        <Panel title="Trial Balance">
          <div style={{ fontSize: 22, fontWeight: 700 }}>{a?.trial_balance_total !== null && a?.trial_balance_total !== undefined ? fmtUsd(a.trial_balance_total / 100) : "—"}</div>
          <div style={{ marginTop: 6 }}>
            <Pill tone={a?.balanced === null || a?.balanced === undefined ? "dim" : a.balanced ? "ok" : "bad"}>
              {a?.balanced === null || a?.balanced === undefined ? "NO LEDGER" : a.balanced ? "BALANCED ✓" : "OUT OF BALANCE ✗"}
            </Pill>
          </div>
        </Panel>
        <Panel title="Open Lots">
          {a?.open_lot_qty && Object.keys(a.open_lot_qty).length > 0 ? (
            Object.entries(a.open_lot_qty).map(([s, q]) => <KV key={s} k={s} v={fmtNum(q)} />)
          ) : (
            <Empty>No open lots.</Empty>
          )}
        </Panel>
        <Panel title="Tax Computation (latest)">
          <KV k="Rule" v={a?.tax.rule_citation ?? "—"} />
          <KV k="Jurisdiction" v={a?.tax.jurisdiction ?? "—"} />
          <KV k="Taxable gain" v={a?.tax.taxable_gain_minor !== null && a?.tax.taxable_gain_minor !== undefined ? fmtUsd(a.tax.taxable_gain_minor / 100) : "—"} />
          <KV k="Tax due" v={a?.tax.tax_due_minor !== null && a?.tax.tax_due_minor !== undefined ? fmtUsd(a.tax.tax_due_minor / 100) : "—"} />
          <KV k="Sign-off" v={<Pill tone={a?.tax.requires_signoff ? "warn" : "ok"}>{a?.tax.requires_signoff ? "REQUIRED" : "OBTAINED"}</Pill>} />
        </Panel>
      </div>
      <Panel title="Ledger Accounts (minor units)">
        <DataTable
          rows={a?.accounts_minor ? Object.entries(a.accounts_minor).map(([account, minor]) => ({ account, minor })) : null}
          rowKey={(r) => r.account}
          empty="No ledger wired in this run."
          columns={[
            { key: "account", label: "Account", render: (r) => <span className="mono">{r.account}</span> },
            { key: "minor", label: "Balance (minor)", numeric: true, render: (r) => fmtNum(r.minor) },
          ]}
        />
      </Panel>
    </>
  );
}

export function TaxReviewPage() {
  const acct = useApi(() => riskApi.accounting());
  const a = acct.data as Accounting | null;

  if (acct.error) return <ErrorBox title="Review queue unavailable" detail={acct.error} />;

  return (
    <>
      <div className="pagehead">
        <h1>Tax & Professional Review</h1>
        <span className="sub">Filing review workflow — a licensed professional must approve before production</span>
      </div>
      <div className="grid cols-2">
        <Panel title="Review Queue">
          <DataTable
            rows={a?.ca_review_queue}
            rowKey={(r) => r.subject_ref}
            empty="No review items queued."
            columns={[
              { key: "subject_ref", label: "Subject", render: (r) => <span className="mono">{r.subject_ref}</span> },
              { key: "state", label: "State", render: (r) => <Pill tone={statusTone(r.state)}>{r.state}</Pill> },
            ]}
          />
        </Panel>
        <Panel title="Constitutional Gate">
          <p className="dim" style={{ fontSize: 12.5, marginTop: 0 }}>
            Live capital remains blocked until a licensed tax professional signs off on the filing rules for the target jurisdiction.
            This gate is held by a human — the engine cannot self-approve it.
          </p>
          <KV k="Current review state" v={<Pill tone={a?.tax.ca_state === "APPROVED_BY_CA" ? "ok" : "warn"}>{a?.tax.ca_state ?? "NOT STARTED"}</Pill>} />
          <KV k="Requires sign-off" v={a?.tax.requires_signoff ? "YES" : "no"} />
        </Panel>
      </div>
    </>
  );
}
