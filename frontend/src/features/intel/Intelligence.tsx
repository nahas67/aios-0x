import { intelligenceApi } from "../../api/endpoints";
import { DataTable, ErrorBox, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDateTime, fmtNum } from "../../lib/format";
import { severityTone } from "../../lib/risk";

export function AgentNetworkPage() {
  const agents = useApi(() => intelligenceApi.agents());
  const rows = agents.data?.agents ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Agent Network</h1>
        <span className="sub">Registered agents across communities with live reputation scores</span>
      </div>
      {agents.error ? (
        <ErrorBox title="Agent network unavailable" detail={agents.error} />
      ) : (
        <Panel title={`Registered Agents${rows ? ` (${rows.length})` : ""}`}>
          <DataTable
            rows={rows}
            rowKey={(r) => r.agent_id}
            empty="No agents registered."
            columns={[
              { key: "agent_id", label: "Agent", render: (r) => <span className="sym">{r.agent_id}</span> },
              { key: "community", label: "Community", render: (r) => <Pill tone="info">{r.community ?? "—"}</Pill> },
              { key: "role", label: "Role" },
              { key: "version", label: "Ver", render: (r) => <span className="mono faint">{r.version ?? "—"}</span> },
              { key: "publishes", label: "Publishes", render: (r) => <span className="dim">{(r.publishes ?? []).join(", ") || "—"}</span> },
              {
                key: "reputation",
                label: "Reputation",
                numeric: true,
                render: (r) =>
                  r.reputation === null || r.reputation === undefined ? (
                    <span className="faint">—</span>
                  ) : (
                    <Pill tone={r.reputation >= 60 ? "ok" : r.reputation >= 30 ? "warn" : "bad"}>{fmtNum(r.reputation)}</Pill>
                  ),
              },
            ]}
          />
        </Panel>
      )}
    </>
  );
}

export function GlobalEventsPage() {
  const events = useApi(() => intelligenceApi.events());
  const rows = events.data?.events ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Global Events</h1>
        <span className="sub">Macro, regime, compliance, emergency, and data events merged newest-first</span>
      </div>
      {events.error ? (
        <ErrorBox title="Events unavailable" detail={events.error} />
      ) : (
        <Panel title={`Event Stream${rows ? ` (${rows.length})` : ""}`}>
          <DataTable
            rows={rows}
            rowKey={(r) => `${r.kind}-${JSON.stringify(r).slice(0, 30)}`}
            empty="No global events recorded yet."
            columns={[
              { key: "label", label: "Source", render: (r) => <Pill tone="info">{r.label}</Pill> },
              { key: "severity", label: "Severity", render: (r) => <Pill tone={severityTone(r.severity)}>{r.severity}</Pill> },
              { key: "title", label: "Event" },
              { key: "symbol", label: "Symbol", render: (r) => (r.symbol ? <span className="sym">{r.symbol}</span> : <span className="faint">—</span>) },
              { key: "ts", label: "Time", render: (r) => <span className="dim">{fmtDateTime(r.ts)}</span> },
            ]}
          />
        </Panel>
      )}
    </>
  );
}

export function AlertsPage() {
  const alerts = useApi(() => intelligenceApi.alerts());
  const rows = alerts.data?.alerts ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Alerts</h1>
        <span className="sub">Critical and warning conditions across all guard rails</span>
      </div>
      {alerts.error ? (
        <ErrorBox title="Alerts unavailable" detail={alerts.error} />
      ) : (
        <Panel title={`Alert Center${rows ? ` (${rows.length})` : ""}`}>
          <DataTable
            rows={rows}
            rowKey={(r) => `${r.category}-${JSON.stringify(r).slice(0, 30)}`}
            empty="No alerts — all guard rails quiet."
            columns={[
              { key: "severity", label: "Severity", render: (r) => <Pill tone={severityTone(r.severity)}>{r.severity}</Pill> },
              { key: "category", label: "Category", render: (r) => <Pill tone="dim">{r.category}</Pill> },
              { key: "message", label: "Message" },
              { key: "symbol", label: "Symbol", render: (r) => (r.symbol ? <span className="sym">{r.symbol}</span> : <span className="faint">—</span>) },
              { key: "ts", label: "Time", render: (r) => <span className="dim">{fmtDateTime(r.ts)}</span> },
            ]}
          />
        </Panel>
      )}
    </>
  );
}

export function PlatformEventsPage() {
  const events = useApi(() => intelligenceApi.platformEvents(150));
  const rows = events.data?.events ?? null;

  return (
    <>
      <div className="pagehead">
        <h1>Platform Events</h1>
        <span className="sub">Typed platform event bus — every contract event, newest first</span>
      </div>
      {events.error ? (
        <ErrorBox title="Platform events unavailable" detail={events.error} />
      ) : (
        <Panel title={`Typed Events${rows ? ` (${rows.length})` : ""}`}>
          <DataTable
            rows={rows}
            rowKey={(r) => `${r.kind}-${JSON.stringify(r).slice(0, 30)}`}
            empty="No platform events yet."
            columns={[
              { key: "kind", label: "Kind", render: (r) => <span className="mono" style={{ fontSize: 11 }}>{r.kind}</span> },
              { key: "occurred_at", label: "Time", render: (r) => <span className="dim">{fmtDateTime(typeof r.occurred_at === "string" ? r.occurred_at : null)}</span> },
              {
                key: "detail",
                label: "Summary",
                render: (r) => {
                  const p = r as Record<string, unknown>;
                  return <span>{String(p.title ?? p.detail ?? p.reason ?? p.summary ?? "—")}</span>;
                },
              },
            ]}
          />
        </Panel>
      )}
    </>
  );
}
