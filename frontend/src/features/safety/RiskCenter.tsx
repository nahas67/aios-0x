import { useState } from "react";
import { riskApi } from "../../api/endpoints";
import { Gauge } from "../../components/charts";
import { DataTable, ErrorBox, Field, KV, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtPct } from "../../lib/format";
import { ACTIONS } from "../../lib/control";
import { getIdentity, ROLE_LEVEL } from "../../stores/identity";
import { ApproveModal } from "../deck/ApproveModal";
import { riskTone } from "../../lib/risk";

export function RiskCenterPage() {
  const risk = useApi(() => riskApi.risk());
  const [confirmAction, setConfirmAction] = useState<string | null>(null);
  const rs = risk.data;

  return (
    <>
      <div className="pagehead">
        <h1>Risk & Safety</h1>
        <span className="sub">Deterministic risk firewall — independent of any LLM, fail-closed</span>
      </div>
      {risk.error ? (
        <ErrorBox title="Risk state unavailable" detail={risk.error} />
      ) : (
        <>
          <div className="grid cols-3" style={{ marginBottom: "var(--gap)" }}>
            <Panel title="Governor State" right={<Pill tone={riskTone(rs?.current_state)}>{rs?.current_state ?? "—"}</Pill>}>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <Gauge
                  label="Drawdown vs halt"
                  valuePct={rs?.drawdown_pct !== null && rs?.drawdown_pct !== undefined && rs?.halt_dd_pct ? (rs.drawdown_pct / rs.halt_dd_pct) * 100 : null}
                  display={rs?.drawdown_pct !== null && rs?.drawdown_pct !== undefined ? `${rs.drawdown_pct.toFixed(2)}% / ${rs.halt_dd_pct ?? "?"}%` : undefined}
                  warnAt={60}
                  badAt={85}
                />
                <KV k="Lockout" v={<Pill tone={rs?.locked_out ? "bad" : "ok"}>{rs?.locked_out ? "ENGAGED" : "CLEAR"}</Pill>} />
                <KV k="Max class exposure" v={rs?.max_class_exposure_pct !== null && rs?.max_class_exposure_pct !== undefined ? fmtPct(rs.max_class_exposure_pct) : "—"} />
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 12, flexWrap: "wrap" }}>
                <button className="btn sm" type="button" onClick={() => setConfirmAction("set_max_position_pct")}>Set exposure limit</button>
                <button className="btn sm" type="button" onClick={() => setConfirmAction("set_halt_drawdown_pct")}>Set halt drawdown</button>
              </div>
            </Panel>

            <Panel title="Per-Class Exposure">
              {rs && Object.keys(rs.class_exposures_pct).length > 0 ? (
                Object.entries(rs.class_exposures_pct).map(([cls, pct]) => (
                  <Gauge
                    key={cls}
                    label={cls}
                    valuePct={rs.max_class_exposure_pct ? (pct / rs.max_class_exposure_pct) * 100 : null}
                    display={`${pct.toFixed(1)}% / ${rs.max_class_exposure_pct ?? "?"}%`}
                    warnAt={70}
                    badAt={90}
                  />
                ))
              ) : (
                <div className="empty">No class exposure data</div>
              )}
            </Panel>

            <Panel title="Emergency Controls" right={<Pill tone="bad">RISK_ADMIN+</Pill>}>
              <p className="dim" style={{ fontSize: 12, marginTop: 0 }}>
                These controls flatten exposure and halt the system. Every use is permanently audited.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <button className="btn danger" type="button" onClick={() => setConfirmAction("trigger_kill_switch")}>
                  TRIGGER KILL SWITCH — flatten all + halt
                </button>
                <button className="btn warn" type="button" onClick={() => setConfirmAction("reset_lockout")}>
                  Reset lockout (after review)
                </button>
              </div>
            </Panel>
          </div>

          <div className="grid cols-2">
            <Panel title="Recent Risk Transitions">
              <DataTable
                rows={rs?.recent_transitions ?? null}
                rowKey={(r) => `${r.new_state}-${JSON.stringify(r).slice(0, 30)}`}
                empty="No transitions recorded."
                columns={[
                  { key: "new_state", label: "State", render: (r) => <Pill tone={riskTone(r.new_state)}>{r.new_state}</Pill> },
                  { key: "reason", label: "Reason" },
                  { key: "triggered_by", label: "By", render: (r) => r.triggered_by ?? "engine" },
                  { key: "lockout_engaged", label: "Lockout", render: (r) => (r.lockout_engaged ? <Pill tone="bad">YES</Pill> : <Pill tone="dim">no</Pill>) },
                ]}
              />
            </Panel>
            <Panel title="Compliance & Emergency Events">
              <EventList title="Compliance" rows={rs?.compliance_alerts ?? []} />
              <EventList title="Emergency" rows={rs?.emergency_events ?? []} />
            </Panel>
          </div>
        </>
      )}

      {confirmAction && (
        <ParamModal
          action={confirmAction}
          needsParam={confirmAction.startsWith("set_")}
          onClose={() => setConfirmAction(null)}
          onDone={() => void risk.refresh()}
        />
      )}
    </>
  );
}

function EventList({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div className="dim" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>{title}</div>
      {rows.length === 0 ? (
        <div className="faint" style={{ fontSize: 12 }}>none recorded</div>
      ) : (
        rows.slice(0, 4).map((p, i) => (
          <div key={i} style={{ fontSize: 12, padding: "3px 0", borderBottom: "1px solid var(--hairline)" }}>
            {String(p.detail ?? p.reason ?? "event")}
          </div>
        ))
      )}
    </div>
  );
}

export function ParamModal({
  action,
  needsParam,
  onClose,
  onDone,
}: {
  action: string;
  needsParam: boolean;
  onClose: () => void;
  onDone?: () => void;
}) {
  const [param, setParam] = useState("");
  const [note, setNote] = useState("");
  const meta = ACTIONS[action];
  const identity = getIdentity();
  const underleveled = ROLE_LEVEL[identity.role] < ROLE_LEVEL[meta?.minRole ?? "ADMIN"];

  return (
    <ApproveModal
      action={action}
      meta={meta}
      onClose={onClose}
      onDone={onDone}
      extraParams={needsParam ? { pct: Number(param) || 0 } : note ? { note } : {}}
      renderBody={(m) => (
        <>
          <p>{m?.describe}</p>
          {needsParam && (
            <Field label="Percentage (0–100]">
              <input
                type="number"
                step="0.5"
                min="0.5"
                max="100"
                value={param}
                onChange={(e) => setParam(e.target.value)}
                placeholder="e.g. 25"
                autoFocus
              />
            </Field>
          )}
          {action === "reset_lockout" && (
            <Field label="Review note (recorded in audit)">
              <input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="why this lockout is cleared" />
            </Field>
          )}
          {underleveled && (
            <p style={{ color: "var(--warn)", fontWeight: 600 }}>
              Role {identity.role} is below {m?.minRole}; the backend will deny this.
            </p>
          )}
        </>
      )}
    />
  );
}
