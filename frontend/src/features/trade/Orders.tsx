import { portfolioApi } from "../../api/endpoints";
import { DataTable, ErrorBox, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDateTime, fmtPrice, fmtUsd, statusTone } from "../../lib/format";

export function OrdersPage() {
  const orders = useApi(() => portfolioApi.orders());
  const rows = orders.data?.orders ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Orders</h1>
        <span className="sub">Every order the engine routed, newest first</span>
      </div>
      {orders.error ? (
        <ErrorBox title="Orders unavailable" detail={orders.error} />
      ) : (
        <Panel title={`Orders${rows ? ` (${rows.length})` : ""}`}>
          <DataTable
            rows={rows}
            rowKey={(r) => r.client_order_id}
            empty="No orders yet."
            columns={[
              { key: "created_at", label: "Time", render: (r) => <span className="dim">{fmtDateTime(r.created_at)}</span> },
              { key: "symbol", label: "Symbol", render: (r) => <span className="sym">{r.symbol}</span> },
              { key: "side", label: "Side", render: (r) => <Pill tone={r.side === "BUY" ? "ok" : "bad"}>{r.side}</Pill> },
              { key: "quantity", label: "Qty", numeric: true },
              { key: "avg_fill_price", label: "Avg fill", numeric: true, render: (r) => fmtPrice(r.avg_fill_price) },
              { key: "status", label: "Status", render: (r) => <Pill tone={statusTone(r.status)}>{r.status}</Pill> },
              { key: "reject_reason", label: "Reject reason", render: (r) => (r.reject_reason ? <span className="neg">{r.reject_reason}</span> : <span className="faint">—</span>) },
            ]}
          />
        </Panel>
      )}
    </>
  );
}

export function OrderValue({ v }: { v: number }) {
  return <span>{fmtUsd(v)}</span>;
}
