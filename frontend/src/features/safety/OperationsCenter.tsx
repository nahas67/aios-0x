import { useState } from "react";
import { executiveApi, portfolioApi } from "../../api/endpoints";
import { DataTable, ErrorBox, Field, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { ACTIONS } from "../../lib/control";
import { ApproveModal } from "../deck/ApproveModal";
import { autonomyTone } from "../../lib/risk";
const AUTONOMY_MODES = ["MANUAL", "ASSISTED", "SUPERVISED", "AUTONOMOUS"] as const;

const MODE_EXPLAIN: Record<string, string> = {
  MANUAL: "Nothing executes. Research may run; no orders are routed.",
  ASSISTED: "Research runs and proposals are generated, but every proposal is rejected pre-trade.",
  SUPERVISED: "Plans queue for explicit human approval before any execution.",
  AUTONOMOUS: "The engine executes within the deterministic risk firewall, without per-plan approval.",
};

export function OperationsCenterPage() {
  const gates = useApi(() => executiveApi.gates());
  const health = useApi(() => executiveApi.health());
  const orders = useApi(() => portfolioApi.orders());
  const [confirm, setConfirm] = useState<{ action: string; params?: Record<string, string | number> } | null>(null);
  const [freezeSymbol, setFreezeSymbol] = useState("");  const autonomy = gates.data?.autonomy ?? null;
  const openOrders = (orders.data?.orders ?? []).filter((o) => !["FILLED", "CANCELLED", "REJECTED"].includes(o.status));

  return (
    <>
      <div className="pagehead">
        <h1>Operations Center</h1>
        <span className="sub">Execution controls — every action audited via the control plane</span>
      </div>

      <div className="grid cols-2" style={{ marginBottom: "var(--gap)" }}>
        <Panel title="Autonomy Mode" right={<Pill tone={autonomyTone(autonomy)}>{autonomy ?? "—"}</Pill>}>
          <p className="dim" style={{ fontSize: 12.5, marginTop: 0 }}>{MODE_EXPLAIN[autonomy ?? ""] ?? "Current mode reported by the control plane."}</p>
          <div className="chips">
            {AUTONOMY_MODES.map((m) => (
              <button
                key={m}
                type="button"
                className={`btn sm ${m === autonomy ? "primary" : ""}`}
                disabled={m === autonomy}
                onClick={() => setConfirm({ action: "set_autonomy", params: { mode: m } })}
              >
                {m}
              </button>
            ))}
          </div>
          <div style={{ marginTop: 10 }}>
            <Field label="Research mode">
              <div className="chips">
                <button className="btn sm" type="button" onClick={() => setConfirm({ action: "set_research_mode", params: { mode: "auto" } })}>auto (LLM debate)</button>
                <button className="btn sm" type="button" onClick={() => setConfirm({ action: "set_research_mode", params: { mode: "deterministic" } })}>deterministic</button>
              </div>
            </Field>
          </div>
        </Panel>

        <Panel title="Execution Controls">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <button className="btn" type="button" onClick={() => setConfirm({ action: "pause_trading" })}>⏸ Pause trading</button>
            <button className="btn ok" type="button" onClick={() => setConfirm({ action: "resume_trading" })}>▶ Resume trading</button>
            <button className="btn warn" type="button" disabled={openOrders.length === 0} onClick={() => setConfirm({ action: "cancel_open_orders" })}>
              ✕ Cancel open orders {openOrders.length > 0 ? `(${openOrders.length})` : ""}
            </button>
          </div>
          <div style={{ marginTop: 12 }}>
            <Field label="Freeze / unfreeze symbol (blocks all activity for it)">
              <input
                type="text"
                placeholder="e.g. BTC/USD"
                value={freezeSymbol}
                onChange={(e) => setFreezeSymbol(e.target.value.toUpperCase())}
              />
            </Field>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                className="btn sm warn"
                type="button"
                disabled={!freezeSymbol}
                onClick={() => setConfirm({ action: "freeze_symbol", params: { symbol: freezeSymbol } })}
              >
                Freeze {freezeSymbol || "symbol"}
              </button>
              <button
                className="btn sm"
                type="button"
                disabled={!freezeSymbol}
                onClick={() => setConfirm({ action: "unfreeze_symbol", params: { symbol: freezeSymbol } })}
              >
                Unfreeze
              </button>
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid cols-2">
        <Panel title="Working Orders">
          <DataTable
            rows={openOrders}
            rowKey={(r) => r.client_order_id}
            empty="No working orders."
            columns={[
              { key: "symbol", label: "Symbol", render: (r) => <span className="sym">{r.symbol}</span> },
              { key: "side", label: "Side", render: (r) => <Pill tone={r.side === "BUY" ? "ok" : "bad"}>{r.side}</Pill> },
              { key: "quantity", label: "Qty", numeric: true },
              { key: "status", label: "Status", render: (r) => <Pill tone="info">{r.status}</Pill> },
            ]}
          />
        </Panel>
        <Panel title="System Health">
          {health.error ? (
            <ErrorBox title="Health unavailable" detail={health.error} />
          ) : health.data ? (
            <>
              <KV k="Audit chain" v={<Pill tone={health.data.audit_chain_valid ? "ok" : "bad"}>{health.data.audit_chain_valid ? "VALID" : `BROKEN @ ${health.data.first_bad_seq}`}</Pill>} />
              <KV k="Ledger wired" v={<Pill tone={health.data.components.ledger_wired ? "ok" : "bad"}>{health.data.components.ledger_wired ? "yes" : "NO"}</Pill>} />
              <KV k="Governor wired" v={<Pill tone={health.data.components.governor_wired ? "ok" : "bad"}>{health.data.components.governor_wired ? "yes" : "NO"}</Pill>} />
              <KV k="Risk governor wired" v={<Pill tone={health.data.components.risk_governor_wired ? "ok" : "bad"}>{health.data.components.risk_governor_wired ? "yes" : "NO"}</Pill>} />
              <KV k="Paper engine wired" v={<Pill tone={health.data.components.paper_engine_wired ? "ok" : "bad"}>{health.data.components.paper_engine_wired ? "yes" : "NO"}</Pill>} />
            </>
          ) : (
            <div className="empty">loading…</div>
          )}
        </Panel>
      </div>

      {confirm && (
        <ApproveModal
          action={confirm.action}
          meta={ACTIONS[confirm.action]}
          extraParams={confirm.params}
          onClose={() => setConfirm(null)}
          onDone={() => {
            void gates.refresh();
            void orders.refresh();
            void health.refresh();
          }}
        />
      )}
    </>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="kv">
      <span className="k">{k}</span>
      <span>{v}</span>
    </div>
  );
}
