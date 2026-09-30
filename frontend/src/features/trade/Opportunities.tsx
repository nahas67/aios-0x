import { intelligenceApi } from "../../api/endpoints";
import { DataTable, ErrorBox, Panel } from "../../components/ui";
import { useApi } from "../../hooks/useApi";

export function OpportunitiesPage() {
  const opps = useApi(() => intelligenceApi.opportunities());
  const rows = opps.data?.opportunities ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Opportunities</h1>
        <span className="sub">Composite-ranked candidates — ranked by the strategy agent each cycle</span>
      </div>
      {opps.error ? (
        <ErrorBox title="Opportunities unavailable" detail={opps.error} />
      ) : (
        <Panel title={`Ranked Opportunities${rows ? ` (${rows.length})` : ""}`}>
          <DataTable
            rows={rows}
            rowKey={(r) => r.strategy_id}
            empty="No ranked opportunities yet — they appear as research cycles complete."
            columns={[
              { key: "composite_rank", label: "Rank", numeric: true },
              { key: "symbol", label: "Symbol", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
              { key: "family", label: "Strategy family" },
              { key: "edge_proxy", label: "Edge", numeric: true, render: (r) => (r.edge_proxy !== null ? r.edge_proxy.toFixed(3) : "—") },
              { key: "expected_rr", label: "R:R", numeric: true, render: (r) => (r.expected_rr !== null ? r.expected_rr.toFixed(2) : "—") },
              { key: "alpha_decay", label: "Decay ×", numeric: true, render: (r) => (r.alpha_decay !== null ? r.alpha_decay.toFixed(2) : "—") },
            ]}
          />
        </Panel>
      )}
    </>
  );
}
