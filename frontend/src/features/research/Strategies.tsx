/**
 * Strategy Center: per-family performance breakdown.
 * Data comes from the engine's realized P&L join — never fabricated.
 */
import { portfolioApi } from "../../api/endpoints";
import { BarChart } from "../../components/charts";
import { DataTable, Empty, ErrorBox, Panel } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtPct, fmtSigned, fmtUsd, pnlClass } from "../../lib/format";

export function StrategiesPage() {
  const strategies = useApi(() => portfolioApi.strategies());
  const pnl = useApi(() => portfolioApi.pnl());
  const rows = strategies.data?.strategies ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Strategies</h1>
        <span className="sub">Per-family performance breakdown — updated as trades close</span>
      </div>
      {strategies.error ? (
        <ErrorBox title="Strategies unavailable" detail={strategies.error} />
      ) : (
        <>
          <div className="grid cols-2" style={{ marginBottom: "var(--gap)" }}>
            <Panel title="P&L by Strategy Family">
              <BarChart
                entries={Object.entries(pnl.data?.by_family ?? {}).map(([label, b]) => ({
                  label,
                  value: b.pnl,
                }))}
                formatValue={(v) => fmtSigned(v, (n) => `$${Math.abs(n).toFixed(0)}`)}
              />
            </Panel>
            <Panel title="Win Rate by Family">
              {rows ? (
                <DataTable
                  rows={rows}
                  rowKey={(r) => r.family}
                  empty="No strategy stats."
                  columns={[
                    { key: "family", label: "Family", render: (r) => <span className="sym">{r.family}</span> },
                    { key: "trades", label: "Trades", numeric: true },
                    { key: "wins", label: "Wins", numeric: true },
                    { key: "losses", label: "Losses", numeric: true },
                    { key: "win_rate_pct", label: "Win rate", numeric: true, render: (r) => <span className={r.win_rate_pct >= 50 ? "pos" : "neg"}>{fmtPct(r.win_rate_pct)}</span> },
                    { key: "pnl", label: "P&L", numeric: true, render: (r) => <span className={pnlClass(r.pnl)}>{fmtSigned(r.pnl, fmtUsd)}</span> },
                  ]}
                />
              ) : (
                <Empty>No strategy performance data yet.</Empty>
              )}
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
