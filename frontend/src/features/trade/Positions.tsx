import { portfolioApi } from "../../api/endpoints";
import { DataTable, ErrorBox, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtPct, fmtPrice, fmtSigned, fmtUsd, pnlClass } from "../../lib/format";

export function PositionsPage() {
  const positions = useApi(() => portfolioApi.positions());
  const rows = positions.data?.positions ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Positions</h1>
        <span className="sub">Open exposure marked against the latest close</span>
      </div>
      {positions.error ? (
        <ErrorBox title="Positions unavailable" detail={positions.error} />
      ) : (
        <Panel title={`Open Positions${rows ? ` (${rows.length})` : ""}`}>
          <DataTable
            rows={rows}
            rowKey={(r) => r.execution_id}
            empty="No open positions — the engine is flat."
            columns={[
              { key: "symbol", label: "Symbol", render: (r) => <span className="sym">{r.symbol}</span> },
              { key: "action", label: "Side", render: (r) => <Pill tone={r.action === "BUY" ? "ok" : "bad"}>{r.action}</Pill> },
              { key: "qty", label: "Qty", numeric: true },
              { key: "entry", label: "Entry", numeric: true, render: (r) => fmtPrice(r.entry) },
              { key: "mark", label: "Mark", numeric: true, render: (r) => fmtPrice(r.mark) },
              {
                key: "unrealized",
                label: "Unrealized",
                numeric: true,
                render: (r) => <span className={pnlClass(r.unrealized)}>{fmtSigned(r.unrealized, fmtUsd)}</span>,
              },
              { key: "mark_value", label: "Value", numeric: true, render: (r) => fmtUsd(r.mark_value) },
              { key: "asset_class", label: "Class", render: (r) => <Pill tone="dim">{r.asset_class}</Pill> },
              { key: "stop", label: "Stop", numeric: true, render: (r) => fmtPrice(r.stop) },
              { key: "target", label: "Target", numeric: true, render: (r) => fmtPrice(r.target) },
            ]}
          />
        </Panel>
      )}
    </>
  );
}

export function PositionPct({ v }: { v: number }) {
  return <span>{fmtPct(v)}</span>;
}
