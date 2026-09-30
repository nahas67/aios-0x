import { useState } from "react";
import { portfolioApi, researchApi } from "../../api/endpoints";

import { DataTable, ErrorBox, KV, Modal, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtPct, fmtPrice, fmtSigned, fmtUsd, pnlClass } from "../../lib/format";

export function ExecutionsPage() {
  const executions = useApi(() => portfolioApi.executions());
  const [selected, setSelected] = useState<string | null>(null);
  const rows = executions.data?.executions ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Decisions & Executions</h1>
        <span className="sub">Closed trades with full provenance — click a row for the decision drilldown</span>
      </div>
      {executions.error ? (
        <ErrorBox title="Executions unavailable" detail={executions.error} />
      ) : (
        <Panel title={`Closed Trades${rows ? ` (${rows.length})` : ""}`}>
          <DataTable
            rows={rows}
            rowKey={(r) => r.execution_id}
            onRowClick={(r) => setSelected(r.execution_id)}
            empty="No closed trades yet."
            columns={[
              { key: "execution_id", label: "Execution", render: (r) => <span className="mono faint">{r.execution_id.slice(0, 13)}…</span> },
              { key: "symbol", label: "Symbol", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
              { key: "action", label: "Side", render: (r) => <Pill tone={r.action === "BUY" ? "ok" : r.action === "SELL" ? "bad" : "dim"}>{r.action ?? "—"}</Pill> },
              { key: "fill_price", label: "Fill", numeric: true, render: (r) => fmtPrice(r.fill_price) },
              { key: "realized_pnl", label: "Realized P&L", numeric: true, render: (r) => <span className={pnlClass(r.realized_pnl)}>{fmtSigned(r.realized_pnl, fmtUsd)}</span> },
              { key: "confidence_pct", label: "Conf", numeric: true, render: (r) => (r.confidence_pct !== null ? fmtPct(r.confidence_pct * 100) : "—") },
              { key: "exit_reason", label: "Exit", render: (r) => <Pill tone={r.exit_reason === "STOP_LOSS" ? "bad" : r.exit_reason === "TAKE_PROFIT" ? "ok" : "dim"}>{r.exit_reason ?? "—"}</Pill> },
            ]}
          />
        </Panel>
      )}
      {selected && <DecisionModal executionId={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

function DecisionModal({ executionId, onClose }: { executionId: string; onClose: () => void }) {
  const detail = useApi(() => researchApi.decisions(executionId));
  const d = detail.data;
  return (
    <Modal title={`Decision ${executionId.slice(0, 16)}…`} onClose={onClose} width={620}>
      {detail.loading && <p className="dim">Loading provenance…</p>}
      {detail.error && <ErrorBox title="Drilldown failed" detail={detail.error} />}
      {d && (
        <>
          <div className="chips" style={{ marginBottom: 10 }}>
            <Pill tone={d.decision.action === "BUY" ? "ok" : "bad"}>{d.decision.action ?? "—"}</Pill>
            <span className="chip">{d.decision.symbol}</span>
            <span className="chip">{d.decision.family}</span>
            <span className="chip">size {fmtPct(d.decision.position_size_pct ?? null)}</span>
            <Pill tone={d.chain_complete ? "ok" : "warn"}>{d.chain_complete ? "CHAIN COMPLETE" : "PARTIAL CHAIN"}</Pill>
          </div>
          <KV k="Thesis" v={<span style={{ maxWidth: 380, display: "inline-block" }}>{d.reason.thesis ?? "—"}</span>} />
          <KV k="Verification conf" v={d.verification.confidence_score !== null ? fmtPct(d.verification.confidence_score * 100) : "—"} />
          <KV k="Fact / balance / math" v={`${fmtScore(d.verification.fact_score)} / ${fmtScore(d.verification.balance_score)} / ${fmtScore(d.verification.math_score)}`} />
          <KV k="Stop / target" v={`${fmtPrice(d.risk.stop_loss_price)} / ${fmtPrice(d.risk.take_profit_price)}`} />
          <KV k="Outcome" v={<span className={pnlClass(d.outcome.actual_pnl)}>{d.outcome.actual_pnl !== null ? fmtSigned(d.outcome.actual_pnl, fmtUsd) : "—"} · {d.outcome.exit_reason ?? "—"}</span>} />
          {d.evidence.supporting_arguments.length > 0 && (
            <>
              <div className="dim" style={{ marginTop: 10, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>Supporting</div>
              {d.evidence.supporting_arguments.slice(0, 4).map((a, i) => (
                <div key={i} style={{ fontSize: 12.5, marginTop: 3 }}>• {a}</div>
              ))}
            </>
          )}
          {d.evidence.counter_arguments.length > 0 && (
            <>
              <div className="dim" style={{ marginTop: 8, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>Counter</div>
              {d.evidence.counter_arguments.slice(0, 4).map((a, i) => (
                <div key={i} style={{ fontSize: 12.5, marginTop: 3 }}>• {a}</div>
              ))}
            </>
          )}
          {d.outcome.lessons_learned.length > 0 && (
            <>
              <div className="dim" style={{ marginTop: 8, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>Lessons learned</div>
              {d.outcome.lessons_learned.slice(0, 4).map((l, i) => (
                <div key={i} style={{ fontSize: 12.5, marginTop: 3 }}>• {l}</div>
              ))}
            </>
          )}
        </>
      )}
    </Modal>
  );
}

function fmtScore(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}
