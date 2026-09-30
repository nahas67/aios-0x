/**
 * TRADE workspaces — Command Deck, Portfolio, Orders & Tape, Opportunities.
 *
 * Deck = the hero surface: equity curve with benchmark + drawdown, P&L
 * attribution (family/symbol), execution tape, open positions — one screen.
 */
import { useEffect, useMemo, useState } from "react";
import {
  executiveApi,
  portfolioApi,
  intelligenceApi,
  riskApi,
  type Equity,
  type Executive,
  type Gates,
  type GlobalEvent,
  type Graduation,
  type Opportunity,
  type Order,
  type Pnl,
  type Portfolio,
  type Position,
  type Regime,
} from "../api";
import {
  Badge,
  BarChart,
  DataTable,
  Empty,
  fmt,
  LineChart,
  PageHead,
  Panel,
  pnlTone,
  Stat,
  toneFor,
  type Col,
} from "../kit";

/* --------------------------------------------------------------- deck data */

function useDeck() {
  const [executive, setExecutive] = useState<Executive | null>(null);
  const [gates, setGates] = useState<Gates | null>(null);
  const [equity, setEquity] = useState<Equity | null>(null);
  const [pnl, setPnl] = useState<Pnl | null>(null);
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [execs, setExecs] = useState<import("../api").Execution[] | null>(null);
  const [regimes, setRegimes] = useState<Regime[] | null>(null);
  const [alerts, setAlerts] = useState<GlobalEvent[] | null>(null);
  const [risk, setRisk] = useState<{ drawdown_pct: number | null } | null>(null);

  useEffect(() => {
    const run = () => {
      executiveApi.get().then(setExecutive).catch(() => undefined);
      executiveApi.gates().then(setGates).catch(() => undefined);
      portfolioApi.equity().then(setEquity).catch(() => undefined);
      portfolioApi.pnl().then(setPnl).catch(() => undefined);
      portfolioApi.positions().then((x) => setPositions(x.positions)).catch(() => undefined);
      portfolioApi.executions().then((x) => setExecs(x.executions)).catch(() => undefined);
      intelligenceApi.regimes().then((x) => setRegimes(x.regimes)).catch(() => undefined);
      intelligenceApi.events().then((x) => setAlerts(x.events)).catch(() => undefined);
      riskApi.risk().then(setRisk).catch(() => undefined);
    };
    run();
    const t = window.setInterval(run, 15_000);
    return () => window.clearInterval(t);
  }, []);

  return { executive, gates, equity, pnl, positions, execs, regimes, alerts, risk };
}

/* ------------------------------------------------------------ command deck */

export function Deck() {
  const d = useDeck();
  const ex = d.executive;
  const equitySeries = useMemo(() => {
    if (!d.equity) return null;
    return [
      { name: "NAV", color: "#4cc2ff", data: d.equity.equity ?? [] },
      { name: "BENCHMARK", color: "#5a6b84", data: d.equity.benchmark ?? [] },
    ];
  }, [d.equity]);

  const ddSeries = useMemo(() => {
    if (!d.equity?.drawdown_pct?.length) return null;
    return [{ name: "DRAWDOWN %", color: "#ffb454", data: d.equity.drawdown_pct }];
  }, [d.equity]);

  const famBars = useMemo(() => {
    if (!d.pnl?.by_family) return [];
    return Object.entries(d.pnl.by_family)
      .map(([label, b]) => ({ label, value: b.pnl }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
  }, [d.pnl]);

  const tapeCols: Col<import("../api").Execution>[] = [
    { key: "sym", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
    { key: "side", head: "SIDE", render: (r) => <Badge tone={(r.action ?? "").toUpperCase() === "SELL" ? "bad" : "ok"}>{r.action ?? "—"}</Badge> },
    { key: "px", head: "PRICE", num: true, render: (r) => fmt.num(r.fill_price, 2) },
    { key: "pnl", head: "REALIZED P&L", num: true, render: (r) => <span className={`v ${pnlTone(r.realized_pnl)}`}>{fmt.moneySigned(r.realized_pnl, 2)}</span> },
    { key: "conf", head: "CONF", num: true, render: (r) => (r.confidence_pct !== null ? `${r.confidence_pct.toFixed(0)}%` : "—") },
    { key: "why", head: "EXIT REASON", render: (r) => <span className="tone-dim">{r.exit_reason ?? "—"}</span> },
    { key: "act", head: "", render: (r) => <TraceLink executionId={r.execution_id} /> },
  ];

  const totalMv = (d.positions ?? []).reduce((a, p) => a + Math.abs(p.mark_value), 0);

  return (
    <>
      <PageHead
        title="Command Deck"
        sub="One screen: performance, risk, tape, world"
        right={<Refresh15s />}
      />

      <div className="statrow" style={{ marginBottom: 12 }}>
        <Stat k="NAV" v={fmt.money(d.equity?.end ?? null, 0)} s={`cash ${fmt.money(ex?.cash_balance, 0)}`} />
        <Stat k="REALIZED P&L" v={fmt.moneySigned(ex?.cumulative_realized_pnl, 0)} tone={pnlTone(ex?.cumulative_realized_pnl) as "pos" | "neg" | "warn" | "info" | undefined} s={`${ex?.closed_trades ?? 0} closed trades`} />
        <Stat k="DRAWDOWN" v={fmt.pct(ex?.drawdown_pct ?? d.risk?.drawdown_pct, 2)} tone={(ex?.drawdown_pct ?? 0) > 1 ? "warn" : undefined} s={`halt at ${fmt.pct(3, 0)}`} />
        <Stat k="OPEN POSITIONS" v={String(ex?.open_positions ?? 0)} s={`gross ${fmt.money(totalMv, 0)}`} />
        <Stat k="AUDIT CHAIN" v={ex?.chain_valid === false ? "BROKEN" : "VALID"} tone={ex?.chain_valid === false ? "neg" : "pos"} s={`${(ex?.events_logged ?? 0).toLocaleString()} events`} />
        <Stat k="PREDICTIONS" v={String(ex?.predictions_scored ?? 0)} s={`${ex?.postmortems ?? 0} postmortems`} />
      </div>

      {d.gates && (
        <div className="notice">
          <span className="tone-dim">EXECUTION</span> <Badge tone={toneFor(d.gates.execution_environment)}>{d.gates.execution_environment}</Badge>
          <span className="tone-dim" style={{ marginLeft: 12 }}>AUTONOMY</span> <Badge tone={toneFor(d.gates.autonomy)}>{d.gates.autonomy}</Badge>
          <span style={{ marginLeft: 12 }} className={d.gates.live_routing_enabled ? "tone-bad" : "tone-dim"}>
            {d.gates.live_routing_enabled ? "⚠ LIVE ROUTING ENABLED" : "no live routing"}
          </span>
        </div>
      )}

      <div className="grid cols-main">
        <Panel
          title="EQUITY CURVE vs BENCHMARK"
          right={d.equity ? <span className="tone-dim">{d.equity.points} pts · {fmt.money(d.equity.start)} → {fmt.money(d.equity.end)}</span> : undefined}
        >
          <div className="panel-b">
            {equitySeries && <LineChart series={equitySeries} height={230} />}
          </div>
        </Panel>
        <Panel title="DRAWDOWN %">
          <div className="panel-b">
            {ddSeries ? <LineChart series={ddSeries} height={230} yFmt={(v) => fmt.pct(v)} /> : <Empty>No drawdown series.</Empty>}
          </div>
        </Panel>
      </div>

      <div className="grid cols-2" style={{ marginTop: 12 }}>
        <Panel title="P&L BY STRATEGY FAMILY" right={d.pnl ? <span className="tone-dim">win rate {fmt.pct(d.pnl.totals?.win_rate_pct, 1)}</span> : undefined}>
          <div className="panel-b">
            {famBars.length ? <BarChart data={famBars} height={170} /> : <Empty>No closed trades yet.</Empty>}
          </div>
        </Panel>
        <Panel title="REGIMES" right={d.regimes ? <span className="tone-dim">{d.regimes.length} symbols</span> : undefined}>
          <div className="panel-b tight">
            <DataTable
              cols={[
                { key: "s", head: "SYMBOL", render: (r: Regime) => <span className="sym">{r.symbol}</span> },
                { key: "t", head: "TREND", render: (r: Regime) => <Badge tone={r.trend === "UP" ? "ok" : r.trend === "DOWN" ? "bad" : "dim"}>{r.trend}</Badge> },
                { key: "v", head: "VOL", render: (r: Regime) => <Badge tone={r.vol_regime === "HIGH" ? "warn" : "dim"}>{r.vol_regime}</Badge> },
                { key: "rv", head: "REALIZED VOL", num: true, render: (r: Regime) => fmt.pct(r.realized_vol_pct) },
              ]}
              rows={d.regimes}
              empty="No regime data."
              max={8}
            />
          </div>
        </Panel>
      </div>

      <div className="grid cols-main" style={{ marginTop: 12 }}>
        <Panel title="EXECUTION TAPE" scroll right={d.execs ? <span className="tone-dim">{d.execs.length} closed</span> : undefined}>
          <DataTable cols={tapeCols} rows={d.execs} empty="No executions yet." max={12} />
        </Panel>
        <Panel title="WORLD EVENTS" scroll>
          <div style={{ padding: "2px 0" }}>
            {(d.alerts ?? []).slice(0, 8).map((e, i) => (
              <div key={i} style={{ padding: "7px 12px", borderBottom: "1px solid var(--line-soft)" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Badge tone={e.severity === "high" ? "bad" : e.severity === "medium" ? "warn" : "dim"}>{e.severity || "info"}</Badge>
                  <span style={{ fontSize: 12 }}>{e.title}</span>
                </div>
                <div className="tone-dim" style={{ fontSize: 10.5, marginTop: 2 }}>
                  {e.kind} · {fmt.short(e.ts)}
                </div>
              </div>
            ))}
            {!d.alerts?.length && <Empty>No world events.</Empty>}
          </div>
        </Panel>
      </div>

      <div style={{ marginTop: 12 }}>
        <Panel title="OPEN POSITIONS" scroll>
          <PositionTable positions={d.positions} />
        </Panel>
      </div>
    </>
  );
}

function Refresh15s() {
  return <span className="tone-dim" style={{ fontSize: 10.5 }}>↻ 15s</span>;
}

/* ---------------------------------------------------------- shared pieces */

export function PositionTable({ positions }: { positions: Position[] | null }) {
  const cols: Col<Position>[] = [
    { key: "sym", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol}</span> },
    { key: "side", head: "SIDE", render: (r) => <Badge tone={r.action === "SELL" ? "bad" : "ok"}>{r.action}</Badge> },
    { key: "qty", head: "QTY", num: true, render: (r) => fmt.qty(r.qty) },
    { key: "entry", head: "ENTRY", num: true, render: (r) => fmt.num(r.entry, 2) },
    { key: "mark", head: "MARK", num: true, render: (r) => fmt.num(r.mark, 2) },
    { key: "mv", head: "MARK VALUE", num: true, render: (r) => fmt.money(r.mark_value, 0) },
    { key: "stop", head: "STOP", num: true, render: (r) => fmt.num(r.stop, 2) },
    { key: "tgt", head: "TARGET", num: true, render: (r) => fmt.num(r.target, 2) },
    { key: "u", head: "UNREALIZED", num: true, render: (r) => <span className={`v ${pnlTone(r.unrealized)}`}>{fmt.moneySigned(r.unrealized, 2)}</span> },
    { key: "cls", head: "CLASS", render: (r) => <Badge tone="dim">{r.asset_class}</Badge> },
  ];
  return <DataTable cols={cols} rows={positions} empty="No open positions." />;
}

export function TraceLink({ executionId }: { executionId: string }) {
  return (
    <button
      className="btn"
      style={{ padding: "2px 8px", fontSize: 10 }}
      onClick={() => {
        window.location.hash = `/trace?id=${encodeURIComponent(executionId)}`;
      }}
    >
      TRACE →
    </button>
  );
}

/* --------------------------------------------------------------- portfolio */

export function PortfolioPage() {
  const [p, setP] = useState<Portfolio | null>(null);
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [grad, setGrad] = useState<Graduation | null>(null);
  const [equity, setEquity] = useState<Equity | null>(null);

  useEffect(() => {
    portfolioApi.portfolio().then(setP).catch(() => undefined);
    portfolioApi.positions().then((x) => setPositions(x.positions)).catch(() => undefined);
    portfolioApi.graduation().then(setGrad).catch(() => undefined);
    portfolioApi.equity().then(setEquity).catch(() => undefined);
  }, []);

  const alloc = useMemo(() => {
    if (!p?.allocation_pct) return [];
    return Object.entries(p.allocation_pct).sort((a, b) => b[1] - a[1]);
  }, [p]);

  return (
    <>
      <PageHead title="Portfolio" sub="Allocation, exposure, graduation criteria" />
      <div className="statrow">
        <Stat k="NAV" v={fmt.money(p?.nav, 2)} />
        <Stat k="CASH" v={fmt.money(p?.cash, 2)} />
        <Stat k="OPEN NOTIONAL" v={fmt.money(p?.open_notional, 0)} />
        <Stat k="EXPOSURE" v={fmt.pct(p?.exposure_pct, 1)} tone={(p?.exposure_pct ?? 0) > 70 ? "warn" : undefined} />
        <Stat k="CLOSED TRADES" v={String(p?.closed_trades ?? 0)} />
        <Stat k="REALIZED P&L" v={fmt.moneySigned(p?.realized_pnl, 2)} tone={pnlTone(p?.realized_pnl) as "pos" | "neg" | "warn" | "info" | undefined} />
      </div>

      <div className="grid cols-2" style={{ marginTop: 12 }}>
        <Panel title="ALLOCATION BY ASSET CLASS">
          <div className="panel-b">
            {alloc.length ? (
              <table className="t">
                <tbody>
                  {alloc.map(([cls, pct]) => (
                    <tr key={cls}>
                      <td style={{ width: 130 }}>{cls}</td>
                      <td>
                        <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.min(100, pct)}%`, background: "var(--cyan)" }} /></div>
                      </td>
                      <td className="num" style={{ width: 76 }}>{fmt.pct(pct, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Empty>No allocation data.</Empty>
            )}
          </div>
        </Panel>
        <Panel title="EQUITY CURVE">
          <div className="panel-b">
            {equity && equity.equity.length > 1 ? (
              <LineChart series={[{ name: "NAV", color: "#4cc2ff", data: equity.equity }]} height={180} />
            ) : (
              <Empty>No equity series.</Empty>
            )}
          </div>
        </Panel>
      </div>

      <div style={{ marginTop: 12 }}>
        <Panel title="OPEN POSITIONS" scroll>
          <PositionTable positions={positions} />
        </Panel>
      </div>

      <div style={{ marginTop: 12 }}>
        <Panel
          title="GRADUATION CRITERIA — PAPER → LIVE"
          right={grad ? <Badge tone={grad.paper_criteria_pass ? "ok" : "warn"}>{grad.paper_criteria_pass ? "ALL PASS" : "NOT MET"}</Badge> : undefined}
        >
          <div className="panel-b tight">
            <DataTable
              cols={[
                { key: "n", head: "CRITERION", render: (r) => r.name },
                { key: "c", head: "CURRENT", num: true, render: (r) => fmt.num(r.current, 2) },
                { key: "op", head: "RULE", render: (r) => <span className="tone-dim">{r.op}</span> },
                { key: "th", head: "THRESHOLD", num: true, render: (r) => fmt.num(r.threshold, 2) },
                { key: "ok", head: "STATUS", render: (r) => <Badge tone={r.pass ? "ok" : "bad"}>{r.pass ? "PASS" : "FAIL"}</Badge> },
              ]}
              rows={grad?.criteria ?? null}
              empty={grad ? "No criteria." : "Loading criteria…"}
            />
          </div>
        </Panel>
      </div>
    </>
  );
}

/* ---------------------------------------------------------- orders & tape */

export function OrdersPage() {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [execs, setExecs] = useState<import("../api").Execution[] | null>(null);

  useEffect(() => {
    portfolioApi.orders().then((x) => setOrders(x.orders)).catch(() => undefined);
    portfolioApi.executions().then((x) => setExecs(x.executions)).catch(() => undefined);
  }, []);

  return (
    <>
      <PageHead title="Orders & Tape" sub="Order lifecycle and closed-trade tape" />
      <div className="grid" style={{ gap: 12 }}>
        <Panel title="ORDERS" scroll tall>
          <DataTable
            cols={[
              { key: "id", head: "CLIENT ORDER ID", render: (r) => <span className="sym" style={{ fontWeight: 400, fontSize: 10.5 }}>{r.client_order_id}</span> },
              { key: "sym", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol}</span> },
              { key: "side", head: "SIDE", render: (r) => <Badge tone={r.side === "SELL" ? "bad" : "ok"}>{r.side}</Badge> },
              { key: "q", head: "QTY", num: true, render: (r) => fmt.qty(r.quantity) },
              { key: "px", head: "AVG FILL", num: true, render: (r) => fmt.num(r.avg_fill_price, 2) },
              { key: "st", head: "STATUS", render: (r) => <Badge tone={toneFor(r.status)}>{r.status}</Badge> },
              { key: "why", head: "REJECT REASON", render: (r) => r.reject_reason ? <span className="tone-bad">{r.reject_reason}</span> : <span className="tone-dim">—</span> },
              { key: "ts", head: "CREATED", render: (r) => <span className="tone-dim">{fmt.ts(r.created_at)}</span> },
            ]}
            rows={orders}
            empty="No orders."
          />
        </Panel>
        <Panel title="CLOSED-TRADE TAPE" scroll>
          <DataTable
            cols={[
              { key: "sym", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
              { key: "side", head: "SIDE", render: (r) => <Badge tone={(r.action ?? "") === "SELL" ? "bad" : "ok"}>{r.action ?? "—"}</Badge> },
              { key: "px", head: "FILL", num: true, render: (r) => fmt.num(r.fill_price, 2) },
              { key: "pnl", head: "REALIZED", num: true, render: (r) => <span className={`v ${pnlTone(r.realized_pnl)}`}>{fmt.moneySigned(r.realized_pnl, 2)}</span> },
              { key: "conf", head: "CONFIDENCE", num: true, render: (r) => (r.confidence_pct !== null ? `${r.confidence_pct.toFixed(0)}%` : "—") },
              { key: "why", head: "EXIT REASON", render: (r) => r.exit_reason ?? "—" },
              { key: "act", head: "", render: (r) => <TraceLink executionId={r.execution_id} /> },
            ]}
            rows={execs}
            empty="No closed trades."
          />
        </Panel>
      </div>
    </>
  );
}

/* ----------------------------------------------------------- opportunities */

export function OpportunitiesPage() {
  const [rows, setRows] = useState<Opportunity[] | null>(null);

  useEffect(() => {
    intelligenceApi.opportunities().then((x) => setRows(x.opportunities)).catch(() => undefined);
  }, []);

  return (
    <>
      <PageHead title="Opportunities" sub="Ranked candidates — composite = edge × R:R × alpha decay" />
      <Panel title="RANKED CANDIDATES" scroll tall>
        <DataTable
          cols={[
            { key: "rank", head: "#", num: true, render: (r) => {
              const idx = (rows ?? []).indexOf(r);
              return idx >= 0 ? idx + 1 : "—";
            } },
            { key: "sym", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
            { key: "fam", head: "FAMILY", render: (r) => <Badge tone="info">{r.family ?? "—"}</Badge> },
            { key: "edge", head: "EDGE PROXY", num: true, render: (r) => fmt.num(r.edge_proxy, 3) },
            { key: "rr", head: "R:R", num: true, render: (r) => fmt.num(r.expected_rr, 2) },
            { key: "dec", head: "ALPHA DECAY", num: true, render: (r) => fmt.num(r.alpha_decay, 3) },
            { key: "comp", head: "COMPOSITE", num: true, render: (r) => <b>{fmt.num(r.composite_rank, 3)}</b> },
          ]}
          rows={rows}
          empty="No ranked opportunities."
        />
      </Panel>
    </>
  );
}
