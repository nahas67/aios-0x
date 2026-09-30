/**
 * SAFETY workspaces — Risk Center, Approvals.
 *
 * Risk Center is the control surface for the risk governor: current state,
 * class exposures vs limits, transitions, emergency controls. Consequential
 * actions run through the shared control runner (audited, RBAC-gated) and
 * require typed confirmation with the action's description shown inline.
 */
import { useCallback, useEffect, useState } from "react";
import { approvalsApi, riskApi, type Approval, type RiskState } from "../api";
import { ACTIONS, runControl } from "../../lib/control";
import { Badge, DataTable, Empty, fmt, PageHead, Panel, Stat } from "../kit";

/* ------------------------------------------------------------- risk center */

const STATES = ["NORMAL", "CAUTION", "WARNING", "HALT", "EMERGENCY_HALT", "LOCKOUT"] as const;

function stateTone(s: string | null | undefined): string {
  const v = (s ?? "").toUpperCase();
  if (v === "NORMAL") return "ok";
  if (["CAUTION", "WARNING"].includes(v)) return "warn";
  if (["HALT", "EMERGENCY_HALT", "LOCKOUT"].includes(v)) return "bad";
  return "dim";
}

const CONTROL_BUTTONS: { action: string; danger?: boolean }[] = [
  { action: "pause_trading" },
  { action: "resume_trading" },
  { action: "cancel_open_orders" },
  { action: "trigger_kill_switch", danger: true },
  { action: "reset_lockout", danger: true },
];

export function RiskCenter() {
  const [risk, setRisk] = useState<RiskState | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    riskApi.risk().then(setRisk).catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    const t = window.setInterval(load, 10_000);
    return () => window.clearInterval(t);
  }, [load]);

  const stateIdx = STATES.indexOf((risk?.current_state ?? "NORMAL").toUpperCase() as (typeof STATES)[number]);

  const act = useCallback(
    async (action: string, params: Record<string, string | number> = {}) => {
      setBusy(true);
      try {
        await runControl(action, params);
        setConfirming(null);
        setText("");
        load();
      } catch {
        /* runControl already toasted the denial/failure */
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const confirmMeta = confirming ? ACTIONS[confirming] : null;

  return (
    <>
      <PageHead title="Risk Center" sub="Risk governor state, exposures, emergency controls" />

      <div className="statrow">
        <Stat k="STATE" v={risk?.current_state ?? "—"} tone={stateTone(risk?.current_state) as "pos" | "neg" | "warn" | "info" | undefined} />
        <Stat
          k="DRAWDOWN"
          v={fmt.pct(risk?.drawdown_pct, 2)}
          tone={risk?.drawdown_pct != null && risk?.halt_dd_pct != null && risk.drawdown_pct > risk.halt_dd_pct ? "neg" : undefined}
          s={`halt at ${fmt.pct(risk?.halt_dd_pct, 1)}`}
        />
        <Stat k="LOCKED OUT" v={risk?.locked_out ? "YES" : "NO"} tone={risk?.locked_out ? "neg" : "pos"} />
        <Stat k="MAX CLASS EXPOSURE" v={fmt.pct(risk?.max_class_exposure_pct, 1)} />
      </div>

      <div className="grid cols-main" style={{ marginTop: 12 }}>
        <Panel title="STATE LADDER">
          <div className="panel-b" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {STATES.map((s, i) => (
              <Badge key={s} tone={i === stateIdx ? stateTone(s) : "dim"} fill={i === stateIdx}>
                {i === stateIdx ? "▶ " : ""}{s}
              </Badge>
            ))}
            <div className="tone-dim" style={{ fontSize: 11, marginTop: 6, width: "100%" }}>
              Escalation is automatic on limit breach; de-escalation requires an audited operator action.
            </div>
          </div>
        </Panel>
        <Panel
          title="CLASS EXPOSURES"
          right={risk?.max_class_exposure_pct != null ? <span className="tone-dim">limit {fmt.pct(risk.max_class_exposure_pct, 0)}</span> : undefined}
        >
          <div className="panel-b">
            {risk && Object.keys(risk.class_exposures_pct).length ? (
              <table className="t">
                <tbody>
                  {Object.entries(risk.class_exposures_pct).map(([cls, pct]) => {
                    const lim = risk.max_class_exposure_pct || 100;
                    return (
                      <tr key={cls}>
                        <td style={{ width: 120 }}>{cls}</td>
                        <td>
                          <div className="bar-track">
                            <div
                              className="bar-fill"
                              style={{
                                width: `${Math.min(100, (pct / lim) * 100)}%`,
                                background: pct >= lim ? "var(--bad)" : pct > 0.7 * lim ? "var(--warn)" : "var(--ok)",
                              }}
                            />
                          </div>
                        </td>
                        <td className="num" style={{ width: 70 }}>{fmt.pct(pct, 1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <Empty>No class exposures.</Empty>
            )}
          </div>
        </Panel>
      </div>

      <div className="grid cols-main" style={{ marginTop: 12 }}>
        <Panel title="RECENT TRANSITIONS" scroll>
          <DataTable
            cols={[
              { key: "s", head: "NEW STATE", render: (r) => <Badge tone={stateTone(r.new_state)}>{r.new_state}</Badge> },
              { key: "r", head: "REASON", render: (r) => <span style={{ fontSize: 11.5 }}>{r.reason}</span> },
              { key: "t", head: "TRIGGERED BY", render: (r) => <span className="tone-dim">{r.triggered_by ?? "auto"}</span> },
              { key: "l", head: "LOCKOUT", render: (r) => (r.lockout_engaged ? <Badge tone="bad">ENGAGED</Badge> : <span className="tone-dim">—</span>) },
            ]}
            rows={risk?.recent_transitions ?? null}
            empty="No transitions."
          />
        </Panel>
        <Panel title="COMPLIANCE & EMERGENCY">
          <div className="panel-b tight">
            <div className="scroll" style={{ maxHeight: 240 }}>
              {(risk?.compliance_alerts ?? []).map((a, i) => (
                <div key={`c${i}`} style={{ padding: "6px 12px", fontSize: 11.5, borderBottom: "1px solid var(--line-soft)" }}>
                  <Badge tone="warn">compliance</Badge>{" "}
                  <span className="tone-dim" style={{ marginLeft: 6 }}>{JSON.stringify(a).slice(0, 120)}</span>
                </div>
              ))}
              {(risk?.emergency_events ?? []).map((e, i) => (
                <div key={`e${i}`} style={{ padding: "6px 12px", fontSize: 11.5, borderBottom: "1px solid var(--line-soft)" }}>
                  <Badge tone="bad">emergency</Badge>{" "}
                  <span className="tone-dim" style={{ marginLeft: 6 }}>{JSON.stringify(e).slice(0, 120)}</span>
                </div>
              ))}
              {!risk?.compliance_alerts.length && !risk?.emergency_events.length && <Empty>No compliance or emergency events.</Empty>}
            </div>
          </div>
        </Panel>
      </div>

      <div style={{ marginTop: 12 }}>
        <Panel title="EMERGENCY CONTROLS" right={<span className="tone-dim">audited · RBAC-gated</span>}>
          <div className="panel-b" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-start" }}>
            {CONTROL_BUTTONS.map(({ action, danger }) => {
              const meta = ACTIONS[action];
              return (
                <button
                  key={action}
                  className={`btn${danger ? " danger" : ""}`}
                  disabled={busy || confirming === action}
                  title={meta?.describe}
                  onClick={() => {
                    setConfirming(action);
                    setText("");
                  }}
                >
                  {meta?.label ?? action}
                </button>
              );
            })}
            {confirming && confirmMeta && (
              <div style={{ width: "100%", border: "1px solid var(--line)", borderRadius: "var(--r)", padding: "10px 12px", background: "var(--panel-2)" }}>
                <div style={{ fontSize: 12, marginBottom: 8 }}>
                  <b className="tone-amber">{confirmMeta.label}</b> — {confirmMeta.describe}{" "}
                  <span className="tone-dim">This is recorded in the audit chain under your identity.</span>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <input className="input" style={{ flex: 1 }} value={text} onChange={(e) => setText(e.target.value)} placeholder={confirmMeta.confirm} autoFocus />
                  <button className="btn primary" disabled={busy || text !== confirmMeta.confirm} onClick={() => void act(confirming)}>
                    {busy ? "EXECUTING…" : "CONFIRM"}
                  </button>
                  <button className="btn" onClick={() => { setConfirming(null); setText(""); }}>CANCEL</button>
                </div>
              </div>
            )}
          </div>
        </Panel>
      </div>
    </>
  );
}

/* --------------------------------------------------------------- approvals */

export function ApprovalsPage() {
  const [rows, setRows] = useState<Approval[] | null>(null);

  useEffect(() => {
    const load = () => approvalsApi.approvals().then((x) => setRows(x.approvals)).catch(() => undefined);
    load();
    const t = window.setInterval(load, 10_000);
    return () => window.clearInterval(t);
  }, []);

  const pending = (rows ?? []).filter((r) => r.status === "PENDING");

  return (
    <>
      <PageHead title="Approvals" sub="Human-held gate — plans awaiting operator decision" />
      <div className="statrow" style={{ marginBottom: 12 }}>
        <Stat k="PENDING" v={String(pending.length)} tone={pending.length ? "warn" : undefined} />
        <Stat k="TOTAL" v={String(rows?.length ?? 0)} />
      </div>
      <Panel title="APPROVAL QUEUE" scroll tall>
        <DataTable
          cols={[
            { key: "id", head: "PLAN ID", render: (r) => <span className="sym" style={{ fontWeight: 400, fontSize: 10.5 }}>{r.plan_id}</span> },
            { key: "sym", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
            { key: "act", head: "ACTION", render: (r) => <Badge tone={r.action === "SELL" ? "bad" : "ok"}>{r.action ?? "—"}</Badge> },
            { key: "px", head: "ENTRY", num: true, render: (r) => fmt.num(r.entry_price, 2) },
            { key: "sz", head: "SIZE %", num: true, render: (r) => fmt.pct(r.position_size_pct, 2) },
            { key: "st", head: "STATUS", render: (r) => <Badge tone={r.status === "PENDING" ? "warn" : r.status === "APPROVED" ? "ok" : r.status === "REJECTED" ? "bad" : "dim"}>{r.status}</Badge> },
          ]}
          rows={rows}
          empty="Queue is empty — nothing awaits a human decision."
        />
      </Panel>
    </>
  );
}
