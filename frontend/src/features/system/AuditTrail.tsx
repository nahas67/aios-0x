/**
 * Audit Trail: immutable hash-chained event log with search.
 * Every mutation is recorded here — operator actions, risk events, research,
 * executions. This is the single source of truth for provenance.
 */
import { useState } from "react";
import { auditApi } from "../../api/endpoints";
import { DataTable, ErrorBox, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDateTime } from "../../lib/format";

const KIND_TONE: Record<string, string> = {
  CONTROL_ACTION: "warn",
  APPROVAL_DECISION: "warn",
  LIVE_CAPITAL_APPROVAL: "bad",
  MODEL_PROMOTED: "ok",
  EVALUATION_RECORD: "info",
  APPROVAL_REQUESTED: "info",
  aios_risk_emergency: "bad",
  aios_c11_compliance_alert: "warn",
};

export function AuditPage() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const audit = useApi(() => auditApi.audit(search, 100), [search]);
  const rows = audit.data?.audit ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Audit Trail</h1>
        <span className="sub">Immutable hash-chained event log — filter by kind or payload text</span>
      </div>
      {audit.error ? (
        <ErrorBox title="Audit unavailable" detail={audit.error} />
      ) : (
        <>
          <div className="toolbar">
            <input
              type="search"
              placeholder="Search by kind or payload…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") setSearch(query); }}
            />
            <button className="btn sm" type="button" onClick={() => setSearch(query)}>Search</button>
            <button className="btn sm" type="button" onClick={() => { setQuery(""); setSearch(""); }}>Clear</button>
            <span className="dim" style={{ fontSize: 11 }}>{rows ? `${rows.length} events` : ""}</span>
          </div>
          <Panel title={`Audit Events`}>
            <DataTable
              rows={rows}
              rowKey={(r) => String(r.seq)}
              empty="No audit events match this query."
              columns={[
                { key: "seq", label: "Seq", numeric: true },
                { key: "ts", label: "Time", render: (r) => <span className="dim">{fmtDateTime(r.ts)}</span> },
                { key: "kind", label: "Kind", render: (r) => <Pill tone={KIND_TONE[r.kind] ?? "dim"}>{r.kind}</Pill> },
                { key: "ref_id", label: "Ref", render: (r) => <span className="mono faint" style={{ fontSize: 11 }}>{r.ref_id ? String(r.ref_id).slice(0, 12) : "—"}</span> },
                {
                  key: "payload",
                  label: "Summary",
                  render: (r) => {
                    const p = r.payload as Record<string, unknown>;
                    const parts: string[] = [];
                    if (p.action) parts.push(String(p.action));
                    if (p.symbol) parts.push(String(p.symbol));
                    if (p.role) parts.push(String(p.role));
                    if (p.authorized !== undefined) parts.push(p.authorized ? "authorized" : "DENIED");
                    if (p.decision) parts.push(String(p.decision));
                    if (p.by) parts.push(`by ${String(p.by)}`);
                    if (p.operator_id) parts.push(String(p.operator_id));
                    return <span>{parts.join(" · ") || <span className="faint">—</span>}</span>;
                  },
                },
                {
                  key: "payload2",
                  label: "Detail",
                  render: (r) => {
                    const p = r.payload as Record<string, unknown>;
                    const result = p.result as Record<string, unknown> | undefined;
                    const detail = p.detail ?? p.reason ?? p.note ?? result?.summary ?? null;
                    return <span className="dim" style={{ fontSize: 11, maxWidth: 260, display: "inline-block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{detail ? String(detail) : "—"}</span>;
                  },
                },
              ]}
            />
          </Panel>
        </>
      )}
    </>
  );
}
