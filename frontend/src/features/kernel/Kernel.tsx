/**
 * Durable financial kernel — operator surfaces (V1-A.2).
 *
 * Six read-only workspaces over the institutional financial kernel: Book of
 * Record, Fills, Cash & Reservations, Reconciliation, Financial Health and Event
 * Delivery.
 *
 * Two rules run through every page here, because the alternative is an operator
 * who trusts a number the system invented:
 *
 * 1. **Unknown is shown as unknown.** Every endpoint can answer
 *    `{ available: false, reason }`; that renders as an explicit unavailable
 *    panel, never as an empty book or a zero. Money that cannot be marked is
 *    `—`, not `$0`.
 * 2. **Broker truth and internal truth are shown side by side.** Reconciliation
 *    is a comparison, so the page shows both sides of every finding rather than
 *    only the verdict.
 */
import { kernelApi } from "../../api/endpoints";
import type { KernelHealth, KernelSafetyState } from "../../api/types";
import { DataTable, Empty, ErrorBox, KV, Panel, Pill, Toolbar } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { agoLabel, fmtDateTime, fmtNum, fmtPrice, fmtSigned, fmtUsd, pnlClass, statusTone } from "../../lib/format";

// --------------------------------------------------------------- primitives

/** Minor units (integer cents) -> display string. Absent stays absent. */
function fmtMinor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return fmtUsd(v / 100);
}

function Dash() {
  return <span className="dim">—</span>;
}

/** One panel shown when a kernel endpoint is not wired into this process. */
function UnavailablePanel({ title, reason }: { title: string; reason: string }) {
  return (
    <Panel title={title}>
      <div className="dim" style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Pill tone="warn">UNAVAILABLE</Pill>
        <span>{reason}</span>
      </div>
    </Panel>
  );
}

function backendLabel(h: KernelHealth | null): string {
  if (!h || h.available !== true) return "unknown";
  if (h.reachable !== true) return "unreachable";
  return h.backend ?? "unknown";
}

function safetyLockouts(safety: KernelSafetyState | null | undefined) {
  return safety?.lockouts ?? [];
}

// ------------------------------------------------------- Book of Record

export function BookOfRecordPage() {
  const book = useApi(() => kernelApi.ibor());
  const data = book.data;

  if (book.error) return <ErrorBox title="Book of Record unavailable" detail={book.error} />;
  if (data && data.available === false) {
    return (
      <>
        <div className="pagehead">
          <h1>Book of Record</h1>
          <span className="sub">Canonical investment book — positions, cash, exposure, NAV</span>
        </div>
        <UnavailablePanel title="Book of Record" reason={data.reason} />
      </>
    );
  }

  const cash = data && data.available ? (data.cash[0] ?? null) : null;
  const marksComplete = data && data.available ? data.marks_complete : null;

  return (
    <>
      <div className="pagehead">
        <h1>Book of Record</h1>
        <span className="sub">
          The single authoritative answer to “what do we own?” — as of{" "}
          {data && data.available ? fmtDateTime(data.as_of) : "unknown"}
        </span>
      </div>

      <Toolbar>
        <Pill tone="dim">account: {data && data.available ? data.account_id : "unknown"}</Pill>
        {marksComplete === null ? (
          <Pill tone="dim">marks: unknown</Pill>
        ) : marksComplete ? (
          <Pill tone="ok">marks complete</Pill>
        ) : (
          <Pill tone="warn">
            marks incomplete — {data && data.available ? data.positions.filter((p) => p.mark_price === null).length : "?"}{" "}
            unmarked
          </Pill>
        )}
        <span className="spacer" />
        <button className="btn ghost" onClick={book.refresh}>
          Refresh
        </button>
      </Toolbar>

      <div className="grid cols-4" style={{ marginBottom: "var(--gap)" }}>
        <Panel>
          <div className="big-num">{data && data.available ? fmtUsd(data.nav) : <Dash />}</div>
          <div className="dim" style={{ fontSize: 11 }}>
            NAV {marksComplete === false ? "(unmarked positions excluded)" : ""}
          </div>
        </Panel>
        <Panel>
          <div className="big-num">{fmtMinor(cash?.available_minor ?? null)}</div>
          <div className="dim" style={{ fontSize: 11 }}>
            available cash (settled {fmtMinor(cash?.settled_minor ?? null)} − reserved{" "}
            {fmtMinor(cash?.reserved_minor ?? null)})
          </div>
        </Panel>
        <Panel>
          <div className="big-num">{data && data.available ? fmtUsd(data.gross_exposure) : <Dash />}</div>
          <div className="dim" style={{ fontSize: 11 }}>
            gross exposure · net {data && data.available ? fmtUsd(data.net_exposure) : "—"}
          </div>
        </Panel>
        <Panel>
          <div className="big-num">{data && data.available ? fmtNum(data.fills_applied) : <Dash />}</div>
          <div className="dim" style={{ fontSize: 11 }}>
            fills applied to the book
          </div>
        </Panel>
      </div>

      <Panel title={`Positions${data && data.available ? ` (${data.positions.length})` : ""}`}>
        <DataTable
          rows={data && data.available ? data.positions : null}
          rowKey={(r) => r.symbol}
          empty="No positions — the book is flat."
          columns={[
            { key: "symbol", label: "Symbol", render: (r) => <span className="sym">{r.symbol}</span> },
            {
              key: "quantity",
              label: "Qty",
              numeric: true,
              render: (r) => <span className={r.quantity < 0 ? "neg" : ""}>{fmtNum(r.quantity)}</span>,
            },
            { key: "avg_cost", label: "Avg cost", numeric: true, render: (r) => fmtPrice(r.avg_cost) },
            {
              key: "mark_price",
              label: "Mark",
              numeric: true,
              render: (r) => (r.mark_price === null ? <Dash /> : fmtPrice(r.mark_price)),
            },
            {
              key: "market_value",
              label: "Market value",
              numeric: true,
              render: (r) => (r.market_value === null ? <Dash /> : fmtUsd(r.market_value)),
            },
            {
              key: "unrealized_pnl",
              label: "Unrealized",
              numeric: true,
              render: (r) =>
                r.unrealized_pnl === null ? (
                  <Dash />
                ) : (
                  <span className={pnlClass(r.unrealized_pnl)}>
                    {fmtSigned(r.unrealized_pnl, fmtUsd)}
                  </span>
                ),
            },
            {
              key: "realized_pnl",
              label: "Realized",
              numeric: true,
              render: (r) => (
                <span className={pnlClass(r.realized_pnl)}>{fmtSigned(r.realized_pnl, fmtUsd)}</span>
              ),
            },
          ]}
        />
      </Panel>

      <Panel title={`Open orders${data && data.available ? ` (${data.open_orders.length})` : ""}`}>
        <DataTable
          rows={data && data.available ? data.open_orders : null}
          rowKey={(r) => r.internal_order_id}
          empty="No live orders."
          columns={[
            { key: "client_order_id", label: "Client id" },
            { key: "symbol", label: "Symbol" },
            { key: "side", label: "Side" },
            { key: "quantity", label: "Qty", numeric: true, render: (r) => fmtNum(r.quantity) },
            {
              key: "filled_quantity",
              label: "Filled",
              numeric: true,
              render: (r) => fmtNum(r.filled_quantity),
            },
            {
              key: "status",
              label: "Status",
              render: (r) => <Pill tone={statusTone(r.status)}>{r.status}</Pill>,
            },
            { key: "version", label: "Ver", numeric: true },
          ]}
        />
      </Panel>
    </>
  );
}

// ------------------------------------------------------------------ Fills

export function FillsPage() {
  const fills = useApi(() => kernelApi.fills(200));
  const data = fills.data;

  if (fills.error) return <ErrorBox title="Fill ledger unavailable" detail={fills.error} />;
  if (data && data.available === false) {
    return (
      <>
        <div className="pagehead">
          <h1>Fills</h1>
          <span className="sub">Immutable execution ledger — the only economic truth</span>
        </div>
        <UnavailablePanel title="Fill ledger" reason={data.reason} />
      </>
    );
  }

  const rows = data && data.available ? data.fills : null;
  const totalNotional = rows?.reduce((a, f) => a + f.quantity * f.price, 0) ?? null;
  const totalFees = rows?.reduce((a, f) => a + f.fee, 0) ?? null;
  const execIds = rows?.map((f) => f.broker_execution_id).filter(Boolean) ?? [];
  const duplicateExecIds = execIds.filter((id, i) => execIds.indexOf(id) !== i);

  return (
    <>
      <div className="pagehead">
        <h1>Fills</h1>
        <span className="sub">
          Every venue execution applied exactly once; the position and cash books are derived from
          this ledger
        </span>
      </div>

      <Toolbar>
        <Pill tone="dim">{rows ? `${rows.length} fills` : "fills unknown"}</Pill>
        <Pill tone="dim">notional {totalNotional === null ? "—" : fmtUsd(totalNotional)}</Pill>
        <Pill tone="dim">fees {totalFees === null ? "—" : fmtUsd(totalFees)}</Pill>
        {duplicateExecIds.length > 0 ? (
          <Pill tone="bad">
            {duplicateExecIds.length} repeated broker execution id(s) in view
          </Pill>
        ) : (
          <Pill tone="ok">no repeated broker execution ids</Pill>
        )}
        <span className="spacer" />
        <button className="btn ghost" onClick={fills.refresh}>
          Refresh
        </button>
      </Toolbar>

      <Panel title="Execution ledger">
        <DataTable
          rows={rows}
          rowKey={(r) => r.fill_id}
          empty="No fills recorded — nothing has executed."
          columns={[
            {
              key: "symbol",
              label: "Symbol",
              render: (r) => <span className="sym">{r.symbol}</span>,
            },
            {
              key: "side",
              label: "Side",
              render: (r) => <Pill tone={r.side === "BUY" ? "ok" : "bad"}>{r.side}</Pill>,
            },
            { key: "quantity", label: "Qty", numeric: true, render: (r) => fmtNum(r.quantity) },
            { key: "price", label: "Price", numeric: true, render: (r) => fmtPrice(r.price) },
            {
              key: "notional",
              label: "Notional",
              numeric: true,
              render: (r) => fmtUsd(r.quantity * r.price),
            },
            { key: "fee", label: "Fee", numeric: true, render: (r) => fmtUsd(r.fee) },
            {
              key: "broker_execution_id",
              label: "Broker exec id",
              render: (r) =>
                r.broker_execution_id ? (
                  <span className="mono">{r.broker_execution_id}</span>
                ) : (
                  <Pill tone="warn">absent</Pill>
                ),
            },
            { key: "account_id", label: "Account" },
            {
              key: "executed_at",
              label: "Executed",
              render: (r) => fmtDateTime(r.executed_at),
            },
          ]}
        />
      </Panel>
    </>
  );
}

// ------------------------------------------------- Cash & Reservations

export function CashReservationsPage() {
  const cash = useApi(() => kernelApi.cash());
  const data = cash.data;

  if (cash.error) return <ErrorBox title="Cash ledger unavailable" detail={cash.error} />;
  if (data && data.available === false) {
    return (
      <>
        <div className="pagehead">
          <h1>Cash &amp; Reservations</h1>
          <span className="sub">Settled, reserved and available buying power</span>
        </div>
        <UnavailablePanel title="Cash ledger" reason={data.reason} />
      </>
    );
  }

  const rows = data && data.available ? data.cash : null;
  const reservations = data && data.available ? data.reservations : null;
  const activeReservations = reservations?.filter((r) => r.active) ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Cash &amp; Reservations</h1>
        <span className="sub">
          Balances derived from the double-entry posting ledger; buying power is settled minus
          reserved
        </span>
      </div>

      <Toolbar>
        <Pill tone="dim">
          {activeReservations ? `${activeReservations.length} active reservation(s)` : "reservations unknown"}
        </Pill>
        <span className="spacer" />
        <button className="btn ghost" onClick={cash.refresh}>
          Refresh
        </button>
      </Toolbar>

      <Panel title="Balances">
        <DataTable
          rows={rows}
          rowKey={(r) => `${r.account_id}:${r.currency}`}
          empty="No cash postings — nothing has been funded."
          columns={[
            { key: "account_id", label: "Account" },
            { key: "currency", label: "Ccy" },
            {
              key: "settled_minor",
              label: "Settled",
              numeric: true,
              render: (r) => fmtMinor(r.settled_minor),
            },
            {
              key: "reserved_minor",
              label: "Reserved",
              numeric: true,
              render: (r) => fmtMinor(r.reserved_minor),
            },
            {
              key: "available_minor",
              label: "Available",
              numeric: true,
              render: (r) => <strong>{fmtMinor(r.available_minor)}</strong>,
            },
          ]}
        />
      </Panel>

      <Panel title="Reservations">
        <DataTable
          rows={reservations}
          rowKey={(r) => r.reservation_id}
          empty="No cash has been reserved."
          columns={[
            { key: "account_id", label: "Account" },
            {
              key: "amount_minor",
              label: "Amount",
              numeric: true,
              render: (r) => fmtMinor(r.amount_minor),
            },
            { key: "currency", label: "Ccy" },
            {
              key: "active",
              label: "State",
              render: (r) => (
                <Pill tone={r.active ? "warn" : "dim"}>{r.active ? "ACTIVE" : "RELEASED"}</Pill>
              ),
            },
            { key: "reason", label: "Reason" },
            {
              key: "order_id",
              label: "Order",
              render: (r) => (r.order_id ? <span className="mono">{r.order_id}</span> : <Dash />),
            },
            { key: "created_at", label: "Created", render: (r) => fmtDateTime(r.created_at) },
          ]}
        />
      </Panel>
    </>
  );
}

// ---------------------------------------------------------- Reconciliation

export function ReconciliationPage() {
  const recon = useApi(() => kernelApi.reconciliation(25));
  const data = recon.data;

  if (recon.error) return <ErrorBox title="Reconciliation unavailable" detail={recon.error} />;
  if (data && data.available === false) {
    return (
      <>
        <div className="pagehead">
          <h1>Reconciliation</h1>
          <span className="sub">Broker truth vs internal truth</span>
        </div>
        <UnavailablePanel title="Reconciliation" reason={data.reason} />
      </>
    );
  }

  const run = data && data.available ? data.last_run : null;
  const findings = data && data.available ? data.open_findings : null;
  const critical = findings?.filter((f) => f.severity === "CRITICAL") ?? null;
  const lockouts = safetyLockouts(data && data.available ? data.lockouts : null);

  // Counts are never used as a proxy for presence: matching is set algebra over
  // execution identities, and the two "only" counters are the set differences.
  const setDiffs =
    run === null
      ? null
      : run.broker_only_executions + run.internal_only_executions;

  return (
    <>
      <div className="pagehead">
        <h1>Reconciliation</h1>
        <span className="sub">
          Set comparison over execution identities, scoped by the venue&apos;s declared coverage
        </span>
      </div>

      <Toolbar>
        {run === null ? (
          <Pill tone="warn">no reconciliation pass recorded</Pill>
        ) : run.ok ? (
          <Pill tone="ok">last pass clean</Pill>
        ) : (
          <Pill tone="bad">last pass raised findings</Pill>
        )}
        {critical && critical.length > 0 ? (
          <Pill tone="bad">{critical.length} critical finding(s) open</Pill>
        ) : null}
        <Pill tone="dim">
          {run ? `last run ${fmtDateTime(run.started_at)}` : "last run unknown"}
        </Pill>
        <span className="spacer" />
        <button className="btn ghost" onClick={recon.refresh}>
          Refresh
        </button>
      </Toolbar>

      <div className="grid cols-2" style={{ marginBottom: "var(--gap)" }}>
        <Panel title="Last pass">
          {run === null ? (
            <Empty>No reconciliation has been recorded for this kernel yet.</Empty>
          ) : (
            <>
              <KV k="Run" v={<span className="mono">{run.run_id}</span>} />
              <KV k="Contract" v={<span className="mono">{run.mode}</span>} />
              <KV k="Broker" v={run.broker ?? "—"} />
              <KV k="Adapter" v={run.adapter_version ?? "unknown"} />
              <KV
                k="Window"
                v={
                  run.window_start && run.window_end
                    ? `${fmtDateTime(run.window_start)} → ${fmtDateTime(run.window_end)}`
                    : run.cursor_token
                      ? `cursor ${run.cursor_token}`
                      : "full snapshot"
                }
              />
              <KV k="Queried at" v={run.queried_at ? fmtDateTime(run.queried_at) : "unknown"} />
              <KV k="Matched executions" v={fmtNum(run.matched_executions)} />
              <KV
                k="Broker-only (absent internally)"
                v={<span className={run.broker_only_executions ? "neg" : ""}>{fmtNum(run.broker_only_executions)}</span>}
              />
              <KV
                k="Internal-only (absent at venue)"
                v={<span className={run.internal_only_executions ? "neg" : ""}>{fmtNum(run.internal_only_executions)}</span>}
              />
              <KV k="Set differences" v={setDiffs === null ? "unknown" : fmtNum(setDiffs)} />
              <KV k="Findings" v={fmtNum(run.finding_count)} />
              <KV
                k="Lockout scope"
                v={
                  run.lockout_scope === "NONE" ? (
                    <Pill tone="ok">NONE</Pill>
                  ) : (
                    <Pill tone="bad">{run.lockout_scope}</Pill>
                  )
                }
              />
            </>
          )}
        </Panel>

        <Panel title="Restricted scopes">
          {lockouts.length === 0 ? (
            <Empty>No active safety-plane restriction.</Empty>
          ) : (
            <DataTable
              rows={lockouts}
              rowKey={(r) => r.lockout_id}
              empty="none"
              columns={[
                {
                  key: "scope",
                  label: "Scope",
                  render: (r) => <Pill tone="bad">{r.scope}</Pill>,
                },
                { key: "subject", label: "Subject", render: (r) => <span className="mono">{r.subject}</span> },
                { key: "reason", label: "Reason" },
                { key: "engaged_by", label: "Engaged by" },
                { key: "engaged_at", label: "Since", render: (r) => fmtDateTime(r.engaged_at) },
              ]}
            />
          )}
        </Panel>
      </div>

      <Panel title={`Open discrepancies${findings ? ` (${findings.length})` : ""}`}>
        <DataTable
          rows={findings}
          rowKey={(r) => r.finding_id}
          empty="No open discrepancies. Broker truth and internal truth agree."
          columns={[
            {
              key: "severity",
              label: "Severity",
              render: (r) => (
                <Pill tone={r.severity === "CRITICAL" ? "bad" : "warn"}>{r.severity}</Pill>
              ),
            },
            { key: "kind", label: "Kind", render: (r) => <span className="mono">{r.kind}</span> },
            { key: "subject", label: "Subject", render: (r) => <span className="mono">{r.subject}</span> },
            {
              key: "internal_value",
              label: "Internal",
              render: (r) => r.internal_value ?? <Pill tone="dim">absent</Pill>,
            },
            {
              key: "broker_value",
              label: "Broker",
              render: (r) => r.broker_value ?? <Pill tone="dim">absent</Pill>,
            },
            { key: "detail", label: "Detail" },
            {
              key: "scope",
              label: "Lockout scope",
              render: (r) => (r.scope === "NONE" ? <Pill tone="dim">NONE</Pill> : <Pill tone="bad">{r.scope}</Pill>),
            },
            { key: "created_at", label: "Opened", render: (r) => fmtDateTime(r.created_at) },
          ]}
        />
      </Panel>

      <Panel title="Recent passes">
        <DataTable
          rows={data && data.available ? data.runs : null}
          rowKey={(r) => r.run_id}
          empty="No passes recorded."
          columns={[
            { key: "started_at", label: "Started", render: (r) => fmtDateTime(r.started_at) },
            { key: "mode", label: "Contract" },
            { key: "matched_executions", label: "Matched", numeric: true },
            { key: "finding_count", label: "Findings", numeric: true },
            {
              key: "ok",
              label: "Result",
              render: (r) => (
                <Pill tone={r.ok ? "ok" : "bad"}>{r.ok ? "CLEAN" : "FINDINGS"}</Pill>
              ),
            },
          ]}
        />
      </Panel>
    </>
  );
}

// -------------------------------------------------------- Financial health

export function FinancialHealthPage() {
  const health = useApi(() => kernelApi.health());
  const invariants = useApi(() => kernelApi.invariants());
  const data = health.data;
  const inv = invariants.data;

  if (health.error) return <ErrorBox title="Financial health unavailable" detail={health.error} />;
  if (data && data.available === false) {
    return (
      <>
        <div className="pagehead">
          <h1>Financial Health</h1>
          <span className="sub">Store, schema, outbox and invariant status</span>
        </div>
        <UnavailablePanel title="Financial health" reason={data.reason} />
      </>
    );
  }

  const schema = data && data.available ? data.schema : undefined;
  const lockouts = safetyLockouts(data && data.available ? data.safety : null);

  return (
    <>
      <div className="pagehead">
        <h1>Financial Health</h1>
        <span className="sub">
          Live status of the durable store and the §61 financial invariants
        </span>
      </div>

      <Toolbar>
        <Pill tone={backendLabel(data) === "unreachable" ? "bad" : "dim"}>
          store: {backendLabel(data)}
        </Pill>
        {schema?.up_to_date === true ? (
          <Pill tone="ok">
            schema v{schema.current ?? "?"}/{schema.required ?? "?"}
          </Pill>
        ) : schema ? (
          <Pill tone="bad">
            schema v{schema.current ?? "?"} of v{schema.required ?? "?"} — migration required
          </Pill>
        ) : (
          <Pill tone="dim">schema unknown</Pill>
        )}
        {inv && inv.available === true ? (
          inv.ok ? (
            <Pill tone="ok">{inv.checked} invariants hold</Pill>
          ) : (
            <Pill tone="bad">{inv.failures.length} invariant failure(s)</Pill>
          )
        ) : (
          <Pill tone="dim">invariants unknown</Pill>
        )}
        <span className="spacer" />
        <button
          className="btn ghost"
          onClick={() => {
            health.refresh();
            invariants.refresh();
          }}
        >
          Re-check
        </button>
      </Toolbar>

      <div className="grid cols-4" style={{ marginBottom: "var(--gap)" }}>
        <Panel>
          <div className="big-num">{data && data.available ? fmtNum(data.outbox_backlog ?? 0) : <Dash />}</div>
          <div className="dim" style={{ fontSize: 11 }}>
            outbox backlog (unpublished committed events)
          </div>
        </Panel>
        <Panel>
          <div className="big-num">{data && data.available ? fmtNum(data.dead_letters ?? 0) : <Dash />}</div>
          <div className="dim" style={{ fontSize: 11 }}>
            dead letters
          </div>
        </Panel>
        <Panel>
          <div className="big-num">{data && data.available ? fmtNum(data.open_findings ?? 0) : <Dash />}</div>
          <div className="dim" style={{ fontSize: 11 }}>
            open reconciliation findings
          </div>
        </Panel>
        <Panel>
          <div className="big-num">{data && data.available ? fmtNum(data.active_lockouts ?? 0) : <Dash />}</div>
          <div className="dim" style={{ fontSize: 11 }}>
            active safety restrictions
          </div>
        </Panel>
      </div>

      <div className="grid cols-2">
        <Panel title="Store">
          {data && data.available ? (
            <>
              <KV k="Backend" v={data.backend ?? "unknown"} />
              <KV
                k="Reachable"
                v={
                  data.reachable === true ? (
                    <Pill tone="ok">yes</Pill>
                  ) : data.reachable === false ? (
                    <Pill tone="bad">no</Pill>
                  ) : (
                    <Pill tone="dim">unknown</Pill>
                  )
                }
              />
              <KV k="Schema dialect" v={schema?.dialect ?? "unknown"} />
              <KV k="Schema version" v={schema ? `${schema.current ?? "?"} / ${schema.required ?? "?"}` : "unknown"} />
              <KV k="Up to date" v={schema?.up_to_date === undefined ? "unknown" : String(schema.up_to_date)} />
            </>
          ) : (
            <Empty>Store status unavailable.</Empty>
          )}
        </Panel>

        <Panel title="Invariants (§61)">
          {inv && inv.available === true ? (
            <>
              <KV k="Checks run" v={fmtNum(inv.checked)} />
              <KV
                k="Result"
                v={inv.ok ? <Pill tone="ok">ALL HOLD</Pill> : <Pill tone="bad">FAILURES</Pill>}
              />
              {inv.failures.length > 0 ? (
                <ul className="kv-list">
                  {inv.failures.map((f) => (
                    <li key={f.name}>
                      <span className="mono">{f.name}</span>
                      <span className="dim"> — {f.detail || "no detail"}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <Empty>
              {inv && inv.available === false ? inv.reason : "Invariant suite not run."}
            </Empty>
          )}
        </Panel>
      </div>

      {lockouts.length > 0 ? (
        <Panel title="Active restrictions">
          <DataTable
            rows={lockouts}
            rowKey={(r) => r.lockout_id}
            empty="none"
            columns={[
              { key: "scope", label: "Scope", render: (r) => <Pill tone="bad">{r.scope}</Pill> },
              { key: "subject", label: "Subject", render: (r) => <span className="mono">{r.subject}</span> },
              { key: "reason", label: "Reason" },
              { key: "engaged_by", label: "Engaged by" },
              { key: "engaged_at", label: "Since", render: (r) => fmtDateTime(r.engaged_at) },
            ]}
          />
        </Panel>
      ) : null}
    </>
  );
}

// --------------------------------------------------------- Event delivery

export function EventDeliveryPage() {
  const outbox = useApi(() => kernelApi.outbox(100));
  const data = outbox.data;
  const backbone = data && data.available ? (data.event_backbone ?? null) : null;

  if (outbox.error) return <ErrorBox title="Event delivery unavailable" detail={outbox.error} />;
  if (data && data.available === false) {
    return (
      <>
        <div className="pagehead">
          <h1>Event Delivery</h1>
          <span className="sub">Transactional outbox: committed events awaiting publication</span>
        </div>
        <UnavailablePanel title="Event delivery" reason={data.reason} />
      </>
    );
  }

  const dead = data && data.available ? data.dead_letters : null;
  const pending = data && data.available ? data.pending : null;
  const publishing = pending?.filter((e) => e.status === "PUBLISHING") ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Event Delivery</h1>
        <span className="sub">
          Events are written in the same transaction as the financial change they describe, then
          published. A backlog here is committed state that has not reached the bus yet.
        </span>
      </div>

      <Toolbar>
        <Pill tone={data && data.available && data.backlog > 0 ? "warn" : "ok"}>
          backlog {data && data.available ? fmtNum(data.backlog) : "unknown"}
        </Pill>
        <Pill tone={dead && dead.length > 0 ? "bad" : "dim"}>
          dead letters {data && data.available ? fmtNum(data.dead_letter_count) : "unknown"}
        </Pill>
        <Pill tone="dim">
          {publishing ? `${publishing.length} claimed (in flight)` : "claims unknown"}
        </Pill>
        {backbone === null ? (
          <Pill tone="dim">transport unknown</Pill>
        ) : backbone.wired === false ? (
          <Pill tone="warn">no durable transport wired</Pill>
        ) : backbone.connected === true ? (
          <Pill tone="ok">jetstream connected</Pill>
        ) : (
          <Pill tone="bad">jetstream disconnected</Pill>
        )}
        <Pill tone={backbone && backbone.consumer_lag ? "warn" : "dim"}>
          consumer lag {backbone?.consumer_lag ?? "unknown"}
        </Pill>
        <span className="spacer" />
        <button className="btn ghost" onClick={outbox.refresh}>
          Refresh
        </button>
      </Toolbar>

      <Panel title="Event backbone">
        {backbone === null ? (
          <Empty>Backbone state not reported by this endpoint.</Empty>
        ) : backbone.wired === false ? (
          <div className="dim" style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Pill tone="warn">NOT WIRED</Pill>
            <span>{backbone.reason ?? "no durable transport in this process"}</span>
          </div>
        ) : (
          <div className="grid cols-4">
            <KV k="Backend" v={backbone.backend ?? "unknown"} />
            <KV
              k="Connected"
              v={
                backbone.connected === true ? (
                  <Pill tone="ok">yes</Pill>
                ) : backbone.connected === false ? (
                  <Pill tone="bad">no</Pill>
                ) : (
                  <Pill tone="dim">unknown</Pill>
                )
              }
            />
            <KV k="Stream" v={backbone.stream ?? "unknown"} />
            <KV k="Server" v={backbone.server ?? "unknown"} />
            <KV k="Published" v={backbone.published === undefined ? "unknown" : fmtNum(backbone.published)} />
            <KV
              k="Publish failures"
              v={backbone.publish_failures === undefined ? "unknown" : fmtNum(backbone.publish_failures)}
            />
            <KV
              k="Reconnects"
              v={backbone.reconnect_count === null || backbone.reconnect_count === undefined ? "unknown" : fmtNum(backbone.reconnect_count)}
            />
            <KV
              k="Consumer lag"
              v={backbone.consumer_lag === null || backbone.consumer_lag === undefined ? <Pill tone="dim">unknown</Pill> : fmtNum(backbone.consumer_lag)}
            />
          </div>
        )}
      </Panel>

      <Panel title={`Dead letters${dead ? ` (${dead.length})` : ""}`}>
        {dead && dead.length === 0 ? (
          <Empty>No dead letters — every committed event has been delivered.</Empty>
        ) : (
          <DataTable
            rows={dead}
            rowKey={(r) => r.event_id}
            empty="none"
            columns={[
              { key: "event_type", label: "Event type", render: (r) => <span className="mono">{r.event_type}</span> },
              { key: "attempts", label: "Attempts", numeric: true },
              { key: "last_error", label: "Last error", render: (r) => r.last_error ?? "—" },
              { key: "event_id", label: "Event id", render: (r) => <span className="mono">{r.event_id}</span> },
            ]}
          />
        )}
      </Panel>

      <Panel title={`Pending publication${pending ? ` (${pending.length})` : ""}`}>
        <DataTable
          rows={pending}
          rowKey={(r) => r.event_id}
          empty="Outbox is empty — everything committed has been published."
          columns={[
            { key: "event_type", label: "Event type", render: (r) => <span className="mono">{r.event_type}</span> },
            {
              key: "status",
              label: "Status",
              render: (r) => (
                <Pill tone={r.status === "PENDING" ? "warn" : "info"}>{r.status}</Pill>
              ),
            },
            { key: "attempts", label: "Attempts", numeric: true },
            {
              key: "claimed_by",
              label: "Claimed by",
              render: (r) => (r.claimed_by ? <span className="mono">{r.claimed_by}</span> : <Dash />),
            },
          ]}
        />
      </Panel>
    </>
  );
}

// ------------------------------------------------- aggregated health strip

/**
 * Compact kernel status for the Command Deck.
 *
 * Consumer lag is reported by the bus, which this process may not own, so it is
 * shown as unknown rather than as zero. Only figures the kernel actually
 * measures appear here.
 */
export function KernelStrip() {
  const health = useApi(() => kernelApi.health());
  const recon = useApi(() => kernelApi.reconciliation(1));
  const invariants = useApi(() => kernelApi.invariants());
  const healthData = health.data;
  const reconData = recon.data;
  const invData = invariants.data;

  if (health.error) {
    return (
      <Panel title="Financial kernel">
        <div className="dim">{health.error}</div>
      </Panel>
    );
  }
  if (healthData && healthData.available === false) {
    return <UnavailablePanel title="Financial kernel" reason={healthData.reason} />;
  }

  const run = reconData && reconData.available ? reconData.last_run : null;
  const lockouts = safetyLockouts(healthData && healthData.available ? healthData.safety : null);

  return (
    <Panel title="Financial kernel">
      <div className="grid cols-4">
        <KV k="Store" v={backendLabel(healthData)} />
        <KV
          k="Schema"
          v={
            healthData && healthData.available && healthData.schema
              ? `v${healthData.schema.current ?? "?"} / v${healthData.schema.required ?? "?"}`
              : "unknown"
          }
        />
        <KV
          k="Outbox backlog"
          v={healthData && healthData.available ? fmtNum(healthData.outbox_backlog ?? 0) : "unknown"}
        />
        <KV
          k="Dead letters"
          v={healthData && healthData.available ? fmtNum(healthData.dead_letters ?? 0) : "unknown"}
        />
        <KV
          k="Open findings"
          v={healthData && healthData.available ? fmtNum(healthData.open_findings ?? 0) : "unknown"}
        />
        <KV
          k="Last reconciliation"
          v={run ? `${fmtDateTime(run.started_at)} (${agoLabel(Date.parse(run.started_at))})` : "never"}
        />
        <KV
          k="Account lockout"
          v={
            lockouts.length === 0 ? (
              <Pill tone="ok">clear</Pill>
            ) : (
              <Pill tone="bad">{lockouts.length} active</Pill>
            )
          }
        />
        <KV
          k="Invariants"
          v={
            invData && invData.available === true ? (
              invData.ok ? (
                <Pill tone="ok">all {invData.checked} hold</Pill>
              ) : (
                <Pill tone="bad">{invData.failures.length} failing</Pill>
              )
            ) : (
              <Pill tone="dim">unknown</Pill>
            )
          }
        />
      </div>
    </Panel>
  );
}
