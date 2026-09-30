/**
 * SYSTEM workspaces — Kernel, Audit, Console, Settings.
 *
 * Kernel surfaces the durable financial kernel with HONEST unavailable states:
 * when the backend answers { available: false, reason } the UI shows exactly
 * that instead of an empty book. Audit shows the hash-chained event log.
 * Console is the natural-language operator chat (RBAC enforced server-side).
 */
import { useEffect, useMemo, useState } from "react";
import {
  auditApi,
  controlApi,
  kernelApi,
  settingsApi,
  type AuditRow,
  type ChatResponse,
  type KernelBookOfRecord,
  type KernelHealth,
  type KernelInvariants,
  type KernelOutbox,
  type KernelReconciliation,
  type SettingsView,
  type Unavailable,
} from "../api";
import { Badge, DataTable, Empty, fmt, PageHead, Panel, Stat, UnavailableBox } from "../kit";
import { getIdentity } from "../../stores/identity";

/* ------------------------------------------------------------------ kernel */

const isAvail = <T extends { available: boolean }>(x: T | Unavailable | null): x is T =>
  x !== null && (x as { available: boolean }).available === true;

export function KernelPage() {
  const [ibor, setIbor] = useState<KernelBookOfRecord | Unavailable | null>(null);
  const [invariants, setInvariants] = useState<KernelInvariants | Unavailable | null>(null);
  const [health, setHealth] = useState<KernelHealth | Unavailable | null>(null);
  const [outbox, setOutbox] = useState<KernelOutbox | Unavailable | null>(null);
  const [recon, setRecon] = useState<KernelReconciliation | Unavailable | null>(null);

  useEffect(() => {
    kernelApi.ibor().then(setIbor).catch(() => undefined);
    kernelApi.invariants().then(setInvariants).catch(() => undefined);
    kernelApi.health().then(setHealth).catch(() => undefined);
    kernelApi.outbox().then(setOutbox).catch(() => undefined);
    kernelApi.reconciliation().then(setRecon).catch(() => undefined);
  }, []);

  const nav = isAvail(ibor) ? ibor.nav : null;
  const marksOk = isAvail(ibor) ? ibor.marks_complete : null;

  return (
    <>
      <PageHead title="Financial Kernel" sub="Durable book of record — exactly-once effects, read-only surface" />

      <div className="statrow" style={{ marginBottom: 12 }}>
        <Stat k="NAV" v={fmt.money(nav, 2)} s={marksOk === false ? "⚠ incomplete marks" : undefined} />
        <Stat k="INVARIANTS" v={isAvail(invariants) ? (invariants.ok ? "PASS" : "FAIL") : "—"} tone={isAvail(invariants) ? (invariants.ok ? "pos" : "neg") : undefined} s={isAvail(invariants) ? `${invariants.checked} checked` : undefined} />
        <Stat k="OUTBOX BACKLOG" v={isAvail(outbox) ? String(outbox.backlog) : "—"} tone={isAvail(outbox) && outbox.backlog > 0 ? "warn" : undefined} />
        <Stat k="DEAD LETTERS" v={isAvail(outbox) ? String(outbox.dead_letter_count) : "—"} tone={isAvail(outbox) && outbox.dead_letter_count > 0 ? "neg" : undefined} />
        <Stat k="RECONCILIATION" v={isAvail(recon) && recon.last_run ? (recon.last_run.ok ? "OK" : "FINDINGS") : "—"} tone={isAvail(recon) && recon.last_run ? (recon.last_run.ok ? "pos" : "warn") : undefined} />
        <Stat k="ACTIVE LOCKOUTS" v={isAvail(recon) && recon.lockouts ? String(recon.lockouts.lockouts?.length ?? 0) : "—"} />
      </div>

      <div className="grid cols-main">
        <Panel
          title="BOOK OF RECORD (IBOR)"
          right={isAvail(ibor) ? <span className="tone-dim">snapshot {ibor.snapshot_id.slice(0, 10)} · as of {fmt.ts(ibor.as_of)}</span> : undefined}
        >
          <div className="panel-b tight">
            {isAvail(ibor) ? (
              <>
                <DataTable
                  cols={[
                    { key: "s", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol}</span> },
                    { key: "q", head: "QTY", num: true, render: (r) => fmt.qty(r.quantity) },
                    { key: "c", head: "AVG COST", num: true, render: (r) => fmt.num(r.avg_cost, 2) },
                    { key: "m", head: "MARK", num: true, render: (r) => fmt.num(r.mark_price, 2) },
                    { key: "mv", head: "MARKET VALUE", num: true, render: (r) => fmt.money(r.market_value) },
                    { key: "u", head: "UNREALIZED", num: true, render: (r) => (
                      <span style={{ color: (r.unrealized_pnl ?? 0) >= 0 ? "var(--ok)" : "var(--bad)" }}>{fmt.moneySigned(r.unrealized_pnl ?? null, 2)}</span>
                    ) },
                    { key: "cur", head: "CCY", render: (r) => <span className="tone-dim">{r.currency}</span> },
                  ]}
                  rows={ibor.positions}
                  empty="No positions in the book."
                />
                <div style={{ padding: "8px 12px", display: "flex", gap: 18, fontSize: 11.5 }} className="tone-dim">
                  <span>cash {ibor.cash.map((c) => `${c.currency} ${fmt.money(c.settled_minor / 100, 2)}`).join(" · ") || "—"}</span>
                  <span>fills applied {ibor.fills_applied}</span>
                  <span>gross {fmt.money(ibor.gross_exposure)}</span>
                  <span>net {fmt.money(ibor.net_exposure)}</span>
                </div>
              </>
            ) : (
              <UnavailableBox reason={ibor?.reason ?? "kernel not wired"} />
            )}
          </div>
        </Panel>

        <div style={{ display: "grid", gap: 12, alignContent: "start" }}>
          <Panel title="INVARIANTS">
            <div className="panel-b tight">
              {isAvail(invariants) ? (
                invariants.failures.length === 0 ? (
                  <div className="empty">✓ all {invariants.checked} invariants hold</div>
                ) : (
                  invariants.failures.map((f, i) => (
                    <div key={i} style={{ padding: "7px 12px", borderBottom: "1px solid var(--line-soft)", fontSize: 11.5 }}>
                      <Badge tone="bad">{f.name}</Badge> <span className="tone-dim">{f.detail}</span>
                    </div>
                  ))
                )
              ) : (
                <UnavailableBox reason={invariants?.reason ?? "unavailable"} />
              )}
            </div>
          </Panel>
          <Panel title="KERNEL HEALTH">
            <div className="panel-b tight">
              {isAvail(health) ? (
                <div style={{ padding: "8px 12px", fontSize: 11.5, display: "grid", gap: 4 }}>
                  <div>backend <b>{health.backend ?? "—"}</b> · reachable <b>{String(health.reachable ?? "—")}</b></div>
                  <div>schema v{health.schema?.current ?? "—"} / {health.schema?.required ?? "—"} {health.schema?.up_to_date === false && <Badge tone="warn">MIGRATION REQUIRED</Badge>}</div>
                  <div>consumer lag <b>{health.event_backbone ? String((health.event_backbone as Record<string, unknown>).consumer_lag ?? "—") : "—"}</b></div>
                  <div>open findings <b>{health.open_findings ?? 0}</b> · lockouts <b>{health.active_lockouts ?? 0}</b></div>
                </div>
              ) : (
                <UnavailableBox reason={health?.reason ?? "unavailable"} />
              )}
            </div>
          </Panel>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 12 }}>
        <Panel title="OUTBOX (EXACTLY-ONCE DELIVERY)" scroll>
          <div className="panel-b tight">
            {isAvail(outbox) ? (
              <>
                {outbox.pending.length > 0 && (
                  <DataTable
                    cols={[
                      { key: "t", head: "EVENT TYPE", render: (r) => <span className="sym" style={{ fontWeight: 400, fontSize: 10.5 }}>{r.event_type}</span> },
                      { key: "s", head: "STATUS", render: (r) => <Badge tone={r.status === "PENDING" ? "warn" : "dim"}>{r.status}</Badge> },
                      { key: "a", head: "ATTEMPTS", num: true, render: (r) => String(r.attempts) },
                    ]}
                    rows={outbox.pending.slice(0, 8)}
                    empty=""
                  />
                )}
                {outbox.dead_letters.length > 0 && (
                  <DataTable
                    cols={[
                      { key: "t", head: "DEAD LETTER", render: (r) => <span className="sym" style={{ fontWeight: 400, fontSize: 10.5, color: "var(--bad)" }}>{r.event_type}</span> },
                      { key: "e", head: "LAST ERROR", render: (r) => <span className="tone-bad" style={{ fontSize: 11 }}>{r.last_error?.slice(0, 60)}</span> },
                      { key: "a", head: "TRIES", num: true, render: (r) => String(r.attempts) },
                    ]}
                    rows={outbox.dead_letters.slice(0, 8)}
                    empty=""
                  />
                )}
                {outbox.pending.length === 0 && outbox.dead_letters.length === 0 && <div className="empty">✓ outbox drained — nothing pending, no dead letters</div>}
              </>
            ) : (
              <UnavailableBox reason={outbox?.reason ?? "unavailable"} />
            )}
          </div>
        </Panel>
        <Panel title="RECONCILIATION — INTERNAL vs BROKER" scroll>
          <div className="panel-b tight">
            {isAvail(recon) ? (
              <>
                <DataTable
                  cols={[
                    { key: "r", head: "RUN", render: (r) => <span className="sym" style={{ fontWeight: 400, fontSize: 10 }}>{r.run_id.slice(0, 12)}…</span> },
                    { key: "m", head: "MODE", render: (r) => <Badge tone="info">{r.mode}</Badge> },
                    { key: "ok", head: "RESULT", render: (r) => (r.ok ? <Badge tone="ok">OK</Badge> : <Badge tone="bad">{r.finding_count} FINDINGS</Badge>) },
                    { key: "f", head: "FINDINGS", num: true, render: (r) => String(r.finding_count) },
                  ]}
                  rows={recon.runs.slice(0, 8)}
                  empty="No reconciliation runs."
                />
                {recon.open_findings.length > 0 && (
                  <div style={{ borderTop: "1px solid var(--line-soft)" }}>
                    {recon.open_findings.slice(0, 6).map((f) => (
                      <div key={f.finding_id} style={{ padding: "6px 12px", fontSize: 11.5, borderBottom: "1px solid var(--line-soft)" }}>
                        <Badge tone={f.severity === "high" ? "bad" : "warn"}>{f.kind}</Badge>{" "}
                        <span style={{ marginLeft: 4 }}>{f.detail.slice(0, 90)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <UnavailableBox reason={recon?.reason ?? "unavailable"} />
            )}
          </div>
        </Panel>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------- audit */

export function AuditPage() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    const t = window.setTimeout(() => {
      auditApi.audit(q, 100).then((x) => setRows(x.audit)).catch(() => undefined);
    }, 250);
    return () => window.clearTimeout(t);
  }, [q]);

  return (
    <>
      <PageHead
        title="Audit"
        sub="Hash-chained event log — tampering breaks the chain and lights the sysbar red"
        right={<input className="input" style={{ width: 260 }} placeholder="filter events…" value={q} onChange={(e) => setQ(e.target.value)} />}
      />
      <Panel title="EVENT LOG" scroll tall>
        <DataTable
          cols={[
            { key: "seq", head: "SEQ", num: true, render: (r) => <span className="tone-dim">{r.seq}</span> },
            { key: "ts", head: "TIME", render: (r) => <span className="tone-dim">{fmt.ts(r.ts)}</span> },
            { key: "kind", head: "KIND", render: (r) => <Badge tone="info">{r.kind}</Badge> },
            { key: "ref", head: "REF", render: (r) => <span className="sym" style={{ fontWeight: 400, fontSize: 10 }}>{r.ref_id ?? "—"}</span> },
            { key: "p", head: "PAYLOAD", render: (r) => <span className="tone-dim" style={{ fontSize: 10.5 }}>{JSON.stringify(r.payload).slice(0, 110)}</span> },
          ]}
          rows={rows}
          empty="No audit events match."
        />
      </Panel>
    </>
  );
}

/* ----------------------------------------------------------------- console */

interface ChatMsg {
  who: "you" | "bot";
  text: string;
  kind?: string;
}

export function ConsolePage() {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useMemo(() => ({ current: null as HTMLDivElement | null }), []);

  const send = async () => {
    const message = input.trim();
    if (!message || busy) return;
    const id = getIdentity();
    setMsgs((m) => [...m, { who: "you", text: message }]);
    setInput("");
    setBusy(true);
    try {
      const res = await controlApi.chat({ operator_id: id.operatorId || "console", role: id.role, message });
      const r = res as ChatResponse;
      setMsgs((m) => [...m, { who: "bot", text: r.answer, kind: r.kind }]);
    } catch (e) {
      setMsgs((m) => [...m, { who: "bot", text: e instanceof Error ? e.message : String(e), kind: "error" }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHead title="Console" sub="Natural-language operations — every command resolves server-side with RBAC" />
      <div className="grid" style={{ gridTemplateColumns: "1fr", gap: 12 }}>
        <Panel title="SESSION LOG" scroll tall>
          <div ref={(el) => { logRef.current = el; }} className="chatlog" style={{ padding: 12 }}>
            {msgs.length === 0 && (
              <Empty>
                Ask about the book, risk state, or run audited commands — try{" "}
                <span className="mono">what is my nav</span> or <span className="mono">pause trading</span>.
              </Empty>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`msg ${m.who}`}>
                <div className="who">
                  {m.who === "you" ? "OPERATOR" : `SYSTEM${m.kind ? ` · ${m.kind.toUpperCase()}` : ""}`}
                </div>
                <div className="txt">{m.text}</div>
              </div>
            ))}
            {busy && <div className="msg bot"><div className="txt tone-dim">thinking…</div></div>}
          </div>
        </Panel>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            className="input"
            style={{ flex: 1 }}
            placeholder="Message the institution…"
            value={input}
            disabled={busy}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void send();
            }}
          />
          <button className="btn primary" disabled={busy || !input.trim()} onClick={() => void send()}>
            SEND
          </button>
        </div>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- settings */

export function SettingsPage() {
  const [s, setS] = useState<SettingsView | null>(null);

  useEffect(() => {
    settingsApi.settings().then(setS).catch(() => undefined);
  }, []);

  const flag = (v: boolean | null | undefined) =>
    v == null ? <span className="tone-dim">—</span> : <Badge tone={v ? "ok" : "dim"}>{v ? "ON" : "OFF"}</Badge>;

  return (
    <>
      <PageHead title="Settings" sub="System configuration — read-only view; changes go through audited control actions" />
      {s ? (
        <div className="grid cols-2">
          <Panel title="SYSTEM">
            <div className="panel-b">
              <dl className="kv">
                <dt>MODEL PROVIDER</dt><dd>{s.system.model_provider}</dd>
                <dt>RESEARCH MODE</dt><dd>{s.system.research_mode}</dd>
                <dt>LLM</dt><dd>{flag(s.system.llm_configured)}</dd>
                <dt>SHADOW MODE</dt><dd>{flag(s.system.shadow_mode)}</dd>
              </dl>
            </div>
          </Panel>
          <Panel title="AI MODELS">
            <div className="panel-b">
              <dl className="kv">
                <dt>RESEARCH CHEAP</dt><dd>{s.ai.research_model_cheap ?? "—"}</dd>
                <dt>RESEARCH REASONING</dt><dd>{s.ai.research_model_reasoning ?? "—"}</dd>
                <dt>VERIFICATION</dt><dd>{s.ai.verification_model ?? "—"}</dd>
                <dt>TEMPERATURE</dt><dd>{s.ai.llm_temperature ?? "—"}</dd>
              </dl>
            </div>
          </Panel>
          <Panel title="DATA PROVIDERS">
            <div className="panel-b">
              <dl className="kv">
                <dt>FINNHUB</dt><dd>{flag(s.data.finnhub)}</dd>
                <dt>GNEWS</dt><dd>{flag(s.data.gnews)}</dd>
                <dt>NEWSDATA</dt><dd>{flag(s.data.newsdata)}</dd>
                <dt>MARKETSTACK</dt><dd>{flag(s.data.marketstack)}</dd>
                <dt>FRED</dt><dd>{flag(s.data.fred)}</dd>
              </dl>
            </div>
          </Panel>
          <Panel title="RISK LIMITS">
            <div className="panel-b">
              <dl className="kv">
                <dt>MAX CLASS EXPOSURE</dt><dd>{fmt.pct(s.risk.max_class_exposure_pct, 1)}</dd>
                <dt>HALT DRAWDOWN</dt><dd>{fmt.pct(s.risk.halt_dd_pct, 2)}</dd>
                <dt>WARNING DRAWDOWN</dt><dd>{fmt.pct(s.risk.warning_dd_pct, 2)}</dd>
                <dt>CAUTION DRAWDOWN</dt><dd>{fmt.pct(s.risk.caution_dd_pct, 2)}</dd>
              </dl>
            </div>
          </Panel>
          <Panel title="EXECUTION RAILS" >
            <div className="panel-b">
              <dl className="kv">
                <dt>ENVIRONMENT</dt><dd><Badge tone={s.execution_rails.environment === "PAPER" ? "info" : "bad"}>{s.execution_rails.environment}</Badge></dd>
                <dt>LIVE ROUTING</dt><dd>{flag(s.execution_rails.live_routing_enabled)}</dd>
                <dt>LIVE CAPITAL APPROVED</dt><dd>{flag(s.execution_rails.live_capital_approval_recorded)}</dd>
                <dt>CONSTITUTION ALLOWS</dt><dd>{flag(s.execution_rails.constitution_live_routing)}</dd>
                <dt>CONSTITUTION PINNED</dt><dd>{flag(s.execution_rails.constitution_pinned)}</dd>
                <dt>MICRO LIVE CAP</dt><dd>{fmt.money(s.execution_rails.micro_live_cap_usd, 0)}</dd>
              </dl>
            </div>
          </Panel>
          <Panel title="AUTONOMY">
            <div className="panel-b">
              <dl className="kv">
                <dt>MODE</dt><dd><Badge tone={s.autonomy === "AUTONOMOUS" ? "warn" : "info"}>{s.autonomy ?? "—"}</Badge></dd>
                <dt>PENDING APPROVALS</dt><dd>{String(s.pending_approvals)}</dd>
              </dl>
              <div className="tone-dim" style={{ fontSize: 11, marginTop: 10 }}>
                Autonomy is changed exclusively through the audited <span className="mono">set_autonomy</span> control action by a RISK_ADMIN or above.
              </div>
            </div>
          </Panel>
        </div>
      ) : (
        <Panel title="SETTINGS"><div className="panel-b"><Empty>Loading…</Empty></div></Panel>
      )}
    </>
  );
}
