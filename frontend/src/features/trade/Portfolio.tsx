import { portfolioApi } from "../../api/endpoints";
import { Donut, LineChart } from "../../components/charts";
import { DataTable, ErrorBox, KV, Panel, Pill, Skeleton } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtPct, fmtSigned, fmtUsd, pnlClass } from "../../lib/format";

export function PortfolioPage() {
  const portfolio = useApi(portfolioApi.portfolio);
  const equity = useApi(portfolioApi.equity);
  const p = portfolio.data;
  const eq = equity.data;

  if (portfolio.loading && !p) return <Skeleton h={200} />;
  if (portfolio.error) return <ErrorBox title="Portfolio unavailable" detail={portfolio.error} />;

  return (
    <>
      <div className="pagehead">
        <h1>Portfolio</h1>
        <span className="sub">Authoritative engine state — cash, exposure, allocation</span>
      </div>
      <div className="grid cols-3" style={{ marginBottom: "var(--gap)" }}>
        <Panel title="Net Asset Value">
          <span className="big-num">{fmtUsd(p?.nav ?? null)}</span>
          <div style={{ marginTop: 8 }}>
            <KV k="Cash" v={fmtUsd(p?.cash ?? null)} />
            <KV k="Open notional" v={fmtUsd(p?.open_notional ?? null)} />
            <KV k="Exposure" v={fmtPct(p?.exposure_pct ?? null)} />
          </div>
        </Panel>
        <Panel title="Realized Performance">
          <span className={`big-num ${pnlClass(p?.realized_pnl ?? null)}`}>{fmtSigned(p?.realized_pnl ?? null, fmtUsd)}</span>
          <div style={{ marginTop: 8 }}>
            <KV k="Closed trades" v={String(p?.closed_trades ?? "—")} />
            <KV k="Data points" v={String(eq?.points ?? "—")} />
          </div>
        </Panel>
        <Panel title="Allocation by Asset Class">
          {p && Object.keys(p.allocation_pct).length ? (
            <Donut entries={Object.entries(p.allocation_pct).map(([label, value]) => ({ label, value }))} size={130} />
          ) : (
            <div className="empty">No open exposure</div>
          )}
        </Panel>
      </div>
      <Panel title="Equity Curve & Drawdown">
        <LineChart
          series={[
            { values: eq?.equity ?? [], color: "#00e5ff", label: "Equity" },
            { values: eq?.benchmark ?? [], color: "#455a64", label: "Benchmark", dashed: true },
          ]}
          height={230}
          formatValue={fmtUsd}
        />
      </Panel>
      <div style={{ marginTop: "var(--gap)" }}>
        <Panel title="Drawdown Series">
          <LineChart series={[{ values: eq?.drawdown_pct ?? [], color: "#ff1744", label: "Drawdown %" }]} height={140} formatValue={(v) => `${v.toFixed(1)}%`} />
        </Panel>
      </div>
      <div style={{ marginTop: "var(--gap)" }}>
        <Panel title="Asset Class Exposure">
          <DataTable
            rows={p ? Object.entries(p.allocation_pct).map(([k, v]) => ({ assetClass: k, pct: v })) : null}
            rowKey={(r) => r.assetClass}
            empty="No exposure"
            columns={[
              { key: "assetClass", label: "Asset class" },
              { key: "pct", label: "Allocation", numeric: true, render: (r) => <Pill tone="info">{fmtPct(r.pct)}</Pill> },
            ]}
          />
        </Panel>
      </div>
    </>
  );
}
