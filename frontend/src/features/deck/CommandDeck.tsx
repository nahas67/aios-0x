/**
 * Command Deck — the flagship overview, matching the Figma prototype:
 * KPI strip, equity curve, AI Intelligence State (thesis + agent stack),
 * Sector Allocation, Risk Controls, Agent Network Debate, Provenance Chain,
 * Real-Time Execution Tape, Macro Regime State. All values are real engine
 * data — never synthesized.
 */
import { useState } from "react";
import { approvalsApi, intelligenceApi, portfolioApi, researchApi, riskApi } from "../../api/endpoints";
import type { Approval, GlobalEvent, Regime } from "../../api/types";
import { Donut, Gauge, LineChart } from "../../components/charts";
import { DataTable, Empty, ErrorBox, Panel, Pill, Skeleton } from "../../components/ui";
import { fmtPct, fmtSigned, fmtUsd, fmtUsdCompact, pnlClass } from "../../lib/format";
import { riskTone } from "../../lib/risk";
import { useApi } from "../../hooks/useApi";
import { ACTIONS } from "../../lib/control";
import { ApproveModal } from "./ApproveModal";
import type { PageProps } from "../../app/nav";

type Range = "1D" | "1W" | "1M" | "3M" | "YTD" | "ALL";
const RANGES: readonly Range[] = ["1D", "1W", "1M", "3M", "YTD", "ALL"];

function sliceCurve(values: number[], range: Range): number[] {
  const n: Record<Range, number> = { "1D": 24, "1W": 7 * 24, "1M": 30, "3M": 90, YTD: 240, ALL: Number.MAX_SAFE_INTEGER };
  return values.slice(-n[range]);
}

export function CommandDeck({ executive, onNavigate }: PageProps) {
  const [range, setRange] = useState<Range>("ALL");
  const [confirmAction, setConfirmAction] = useState<string | null>(null);

  const portfolio = useApi(portfolioApi.portfolio);
  const equity = useApi(portfolioApi.equity);
  const risk = useApi(riskApi.risk);
  const regimes = useApi(intelligenceApi.regimes);
  const events = useApi(intelligenceApi.events);
  const approvals = useApi(approvalsApi.approvals);

  const p = portfolio.data;
  const eq = equity.data;
  const rs = risk.data;

  const nav = p?.nav ?? executive?.cash_balance ?? null;
  const dd = executive?.drawdown_pct ?? rs?.drawdown_pct ?? null;
  const haltDd = rs?.halt_dd_pct ?? null;
  const distToHalt = dd !== null && haltDd !== null ? Math.max(0, haltDd - dd) : null;

  const visibleApprovals: Approval[] = (approvals.data as { approvals?: Approval[] })?.approvals ?? [];

  return (
    <>
      <div className="pagehead">
        <h1>Command Deck</h1>
        <span className="sub">Live engine state · paper/shadow · execution gated by autonomy + risk firewall</span>
      </div>

      <div className="grid cols-23" style={{ marginBottom: "var(--gap)" }}>
        <Panel
          title="Portfolio Net Asset Value"
          right={<Pill tone={riskTone(executive?.emergency_state)}>{executive?.emergency_state ?? "—"}</Pill>}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
            <span className="big-num">{nav === null ? "—" : fmtUsd(nav)}</span>
            {p && (
              <span className={pnlClass(p.realized_pnl)} style={{ fontWeight: 700 }}>
                {fmtSigned(p.realized_pnl, fmtUsdCompact)} realized
              </span>
            )}
          </div>
          <div className="chips" style={{ margin: "8px 0 10px" }}>
            <span className="chip">Cash {fmtUsd(p?.cash ?? executive?.cash_balance)}</span>
            <span className="chip">Open positions {executive?.open_positions ?? "—"}</span>
            <span className="chip">Exposure {fmtPct(p?.exposure_pct ?? null)}</span>
            <span className="chip">Trades {executive?.closed_trades ?? "—"}</span>
          </div>
          <LineChart
            series={[{ values: sliceCurve(eq?.equity ?? [], range), color: "#00e5ff", label: "Equity" }]}
            height={190}
            formatValue={fmtUsdCompact}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
            <span className="faint" style={{ fontSize: 11 }}>
              {eq && eq.points > 0 ? `${eq.points} recorded points · start ${fmtUsdCompact(eq.start)} → end ${fmtUsdCompact(eq.end)}` : "no equity points recorded"}
            </span>
            <div className="tabs">
              {RANGES.map((r) => (
                <button key={r} type="button" className={r === range ? "active" : ""} onClick={() => setRange(r)}>
                  {r}
                </button>
              ))}
            </div>
          </div>
        </Panel>

        <Panel title="AI Intelligence State" right={<Pill tone="info">DETERMINISTIC+LLM</Pill>}>
          <ActiveThesis />
        </Panel>
      </div>

      <div className="grid cols-3" style={{ marginBottom: "var(--gap)" }}>
        <Panel title="Sector Allocation & Exposures">
          {p && Object.keys(p.allocation_pct).length > 0 ? (
            <Donut entries={Object.entries(p.allocation_pct).map(([label, value]) => ({ label, value }))} />
          ) : (
            <Empty>No open exposure — allocation appears as positions are opened.</Empty>
          )}
          <div style={{ marginTop: 10 }}>
            <KVRow k="Open notional" v={fmtUsd(p?.open_notional ?? null)} />
            <KVRow k="Closed trades" v={String(p?.closed_trades ?? "—")} />
          </div>
        </Panel>

        <Panel title="Risk Controls" right={<Pill tone={riskTone(rs?.current_state)}>{rs?.current_state ?? "—"}</Pill>}>
          <Gauge label="Drawdown / halt limit" valuePct={dd !== null && haltDd !== null ? (dd / haltDd) * 100 : null} display={dd !== null && haltDd !== null ? `${dd.toFixed(2)}% / ${haltDd.toFixed(1)}%` : undefined} warnAt={60} badAt={85} />
          <div style={{ height: 8 }} />
          <Gauge
            label="Max class exposure"
            valuePct={(() => {
              const lim = rs?.max_class_exposure_pct;
              if (!lim || !rs?.class_exposures_pct) return null;
              const worst = Math.max(0, ...Object.values(rs.class_exposures_pct));
              return (worst / lim) * 100;
            })()}
            warnAt={70}
            badAt={90}
          />
          <div style={{ height: 8 }} />
          <KVRow
            k="Distance to emergency halt"
            v={<span style={{ color: distToHalt !== null && distToHalt < 2 ? "var(--bad)" : "var(--warn)", fontWeight: 700 }}>{distToHalt === null ? "—" : `${distToHalt.toFixed(2)}%`}</span>}
          />
          <KVRow k="Lockout" v={<Pill tone={rs?.locked_out ? "bad" : "ok"}>{rs?.locked_out ? "ENGAGED" : "CLEAR"}</Pill>} />
          <KVRow k="Events logged" v={String(executive?.events_logged ?? "—")} />
          <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button className="btn sm" type="button" onClick={() => onNavigate?.("risk")}>
              Risk center →
            </button>
            <button
              className="btn sm danger"
              type="button"
              onClick={() => setConfirmAction("trigger_kill_switch")}
            >
              KILL SWITCH
            </button>
          </div>
        </Panel>

        <Panel title="Agent Network Debate" right={<span className="faint" style={{ fontSize: 11 }}>live hypotheses</span>}>
          <DebatePanel />
        </Panel>
      </div>

      <div className="grid cols-3">
        <Panel title="Decision Provenance Chain" right={<Pill tone="info">audit-linked</Pill>}>
          <ProvenancePanel events={(events.data as { events?: GlobalEvent[] })?.events ?? null} />
        </Panel>

        <Panel title="Real-Time Execution Tape" right={<button className="btn sm" type="button" onClick={() => onNavigate?.("executions")}>All →</button>}>
          <TapePanel />
        </Panel>

        <Panel title="Macro-Market Regime State">
          <RegimePanel regimes={regimes.data?.regimes ?? null} />
        </Panel>
      </div>

      {visibleApprovals.length > 0 && (
        <div style={{ marginTop: "var(--gap)" }}>
          <Panel
            title={`Pending Approvals (${visibleApprovals.length})`}
            right={<button className="btn sm primary" type="button" onClick={() => onNavigate?.("approvals")}>Open queue →</button>}
          >
            <div className="chips">
              {visibleApprovals.slice(0, 4).map((a) => (
                <span key={a.plan_id} className="chip">
                  <strong style={{ color: "var(--cyan)" }}>{a.action}</strong> {a.symbol} · {fmtPct(a.position_size_pct)}
                </span>
              ))}
            </div>
          </Panel>
        </div>
      )}

      {confirmAction && (
        <ApproveModal
          action={confirmAction}
          meta={ACTIONS[confirmAction]}
          onClose={() => setConfirmAction(null)}
          onDone={() => {
            void risk.refresh();
            void portfolio.refresh();
          }}
          renderBody={(meta) => (
            <>
              <p>{meta?.describe}</p>
              {confirmAction === "trigger_kill_switch" && (
                <p style={{ color: "var(--bad)", fontWeight: 700 }}>
                  This flattens every open position at adverse prices and halts the system.
                </p>
              )}
            </>
          )}
        />
      )}
    </>
  );
}

function KVRow({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="kv">
      <span className="k">{k}</span>
      <span>{v}</span>
    </div>
  );
}

function ActiveThesis() {
  const knowledge = useApi(() => researchApi.knowledge());
  const k = knowledge.data;
  if (knowledge.loading) return <Skeleton h={60} />;
  if (knowledge.error) return <ErrorBox title="Research plane unavailable" detail={knowledge.error} />;
  if (!k?.available || !k.recent?.length) {
    return <Empty>No hypotheses yet — research engine publishes them here as cycles complete.</Empty>;
  }
  const top = k.recent[0];
  const conf = top.confidence !== null ? Math.round(top.confidence * 100) : null;
  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ color: "var(--cyan)", fontWeight: 600, fontSize: 12.5 }}>
          ACTIVE THESIS: {top.symbol ?? "—"}
        </span>
        <Pill tone={conf !== null && conf >= 60 ? "ok" : "warn"}>{conf !== null ? `${conf}% THESIS CONF` : "CONF —"}</Pill>
      </div>
      <p style={{ margin: "0 0 10px", fontSize: 12.5, color: "var(--text)" }}>{top.statement}</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {k.recent.slice(0, 5).map((h) => (
          <div key={h.hypothesis_id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
            <span className="dim" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "60%" }}>
              {h.statement.slice(0, 60)}
            </span>
            <Pill tone={h.status === "VALIDATED" ? "ok" : h.status === "REFUTED" ? "bad" : "dim"}>{h.status}</Pill>
          </div>
        ))}
      </div>
    </>
  );
}

function DebatePanel() {
  const knowledge = useApi(() => researchApi.knowledge());
  const k = knowledge.data;
  if (knowledge.loading) return <Skeleton />;
  if (knowledge.error) return <ErrorBox title="Debate unavailable" detail={knowledge.error} />;
  const rows = k?.recent ?? [];
  if (!rows.length) return <Empty>Agent debate output appears here once research cycles run.</Empty>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {rows.slice(0, 4).map((h, i) => {
        const conf = h.confidence !== null ? Math.round(h.confidence * 100) : null;
        const bull = h.status !== "REFUTED";
        return (
          <div key={i} style={{ borderBottom: "1px solid var(--hairline)", paddingBottom: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontWeight: 600, fontSize: 11.5, color: bull ? "var(--ok)" : "var(--bad)" }}>
                {bull ? "SYS_BULL" : "SYS_BEAR"} [{h.status}]
              </span>
              {conf !== null && <span className="faint" style={{ fontSize: 11 }}>{conf}% conviction</span>}
            </div>
            <div style={{ fontSize: 12, marginTop: 2 }}>"{h.statement.slice(0, 110)}"</div>
          </div>
        );
      })}
    </div>
  );
}

function ProvenancePanel({ events }: { events: GlobalEvent[] | null }) {
  if (!events) return <Skeleton />;
  if (!events.length) return <Empty>No global events yet.</Empty>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {events.slice(0, 5).map((e, i) => (
        <div key={i} style={{ display: "flex", gap: 8, padding: "5px 0", borderBottom: "1px solid var(--hairline)" }}>
          <Pill tone="info">{e.label}</Pill>
          <span style={{ fontSize: 12, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.title}</span>
          <span className="faint" style={{ fontSize: 11 }}>{e.ts ? new Date(e.ts).toLocaleTimeString([], { hour12: false }) : ""}</span>
        </div>
      ))}
    </div>
  );
}

function TapePanel() {
  const executions = useApi(() => portfolioApi.executions());
  const rows = executions.data?.executions ?? null;
  return (
    <DataTable
      rows={rows?.slice(0, 6)}
      rowKey={(r) => r.execution_id}
      empty="No closed executions yet — the tape fills as trades complete."
      columns={[
        { key: "symbol", label: "Symbol", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
        {
          key: "action",
          label: "Side",
          render: (r) => <Pill tone={r.action === "BUY" ? "ok" : r.action === "SELL" ? "bad" : "dim"}>{r.action ?? "—"}</Pill>,
        },
        { key: "realized_pnl", label: "P&L", numeric: true, render: (r) => <span className={pnlClass(r.realized_pnl)}>{fmtSigned(r.realized_pnl, fmtUsd)}</span> },
        { key: "exit_reason", label: "Exit", render: (r) => <span className="dim">{r.exit_reason ?? "—"}</span> },
      ]}
    />
  );
}

function RegimePanel({ regimes }: { regimes: Regime[] | null }) {
  if (!regimes) return <Skeleton />;
  if (!regimes.length) return <Empty>No regime data — engine computes per-symbol state from closes.</Empty>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {regimes.map((r) => (
        <div key={r.symbol} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
          <span className="sym" style={{ width: 62 }}>{r.symbol}</span>
          <span style={{ flex: 1, fontSize: 12 }} className="dim">
            {r.trend} · vol {r.realized_vol_pct !== null ? `${Number(r.realized_vol_pct).toFixed(1)}%` : "—"}
          </span>
          <Pill tone={r.vol_regime === "HIGH" ? "warn" : r.trend === "TRENDING" ? "ok" : "dim"}>{r.vol_regime}</Pill>
        </div>
      ))}
    </div>
  );
}
