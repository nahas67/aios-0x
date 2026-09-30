/**
 * INTEL workspaces — Agents, World, Memory.
 *
 * "Know Your Agent": every agent's role, version, publishes, reputation.
 * World = the market context the institution reacts to.
 */
import { useEffect, useMemo, useState } from "react";
import {
  intelligenceApi,
  modelsApi,
  type Agent,
  type Alert,
  type EvaluationRecord,
  type GlobalEvent,
  type ModelVersion,
  type PlatformEvent,
  type Regime,
} from "../api";
import { Badge, DataTable, DistBar, Empty, fmt, PageHead, Panel, Stat, toneFor } from "../kit";

/* ------------------------------------------------------------------ agents */

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [models, setModels] = useState<ModelVersion[] | null>(null);
  const [evals, setEvals] = useState<EvaluationRecord[] | null>(null);

  useEffect(() => {
    intelligenceApi.agents().then((x) => setAgents(x.agents)).catch(() => undefined);
    modelsApi.models().then((x) => setModels(x.models ?? [])).catch(() => undefined);
    modelsApi.evaluations().then((x) => setEvals(x.evaluations)).catch(() => undefined);
  }, []);

  const byCommunity = useMemo(() => {
    const m = new Map<string, number>();
    for (const a of agents ?? []) {
      const c = a.community ?? "—";
      m.set(c, (m.get(c) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [agents]);

  return (
    <>
      <PageHead title="Agents" sub="Know Your Agent — who proposes, what they publish, what they're worth" />
      <div className="statrow">
        <Stat k="AGENTS" v={String(agents?.length ?? 0)} />
        <Stat k="COMMUNITIES" v={String(byCommunity.length)} />
        <Stat k="MODELS" v={String(models?.length ?? 0)} />
        <Stat k="EVALUATIONS" v={String(evals?.length ?? 0)} />
      </div>

      <div className="grid cols-main" style={{ marginTop: 12 }}>
        <Panel title="AGENT ROSTER" scroll tall>
          <DataTable
            cols={[
              { key: "id", head: "AGENT ID", render: (r) => <span className="sym">{r.agent_id}</span> },
              { key: "c", head: "COMMUNITY", render: (r) => <Badge tone="info">{r.community ?? "—"}</Badge> },
              { key: "r", head: "ROLE", render: (r) => <span className="tone-dim">{r.role ?? "—"}</span> },
              { key: "v", head: "VERSION", render: (r) => <span className="tone-dim">{r.version ?? "—"}</span> },
              { key: "p", head: "PUBLISHES", render: (r) => (
                <span style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  {r.publishes.map((p) => <Badge key={p} tone="dim">{p}</Badge>)}
                </span>
              ) },
              { key: "rep", head: "REPUTATION", num: true, render: (r) => fmt.num(r.reputation, 2) },
            ]}
            rows={agents}
            empty="No agents registered."
          />
        </Panel>
        <div style={{ display: "grid", gap: 12, alignContent: "start" }}>
          <Panel title="BY COMMUNITY">
            <div className="panel-b">
              {byCommunity.length ? (
                <table className="t">
                  <tbody>
                    {byCommunity.map(([c, n]) => (
                      <tr key={c}>
                        <td style={{ width: 150 }}>{c}</td>
                        <td>
                          <div className="bar-track"><div className="bar-fill" style={{ width: `${(n / (agents?.length || 1)) * 100}%`, background: "var(--cyan)" }} /></div>
                        </td>
                        <td className="num" style={{ width: 40 }}>{n}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Empty>No agents yet.</Empty>
              )}
            </div>
          </Panel>
          <Panel title="MODEL REGISTRY" right={models ? <span className="tone-dim">{models.length}</span> : undefined}>
            <div className="panel-b tight">
              <DataTable
                cols={[
                  { key: "id", head: "MODEL", render: (r) => <span className="sym" style={{ fontSize: 10.5 }}>{r.model_id}</span> },
                  { key: "v", head: "VER", render: (r) => <span className="tone-dim">{r.version}</span> },
                  { key: "s", head: "STATUS", render: (r) => <Badge tone={toneFor(r.status)}>{r.status}</Badge> },
                ]}
                rows={models}
                empty="No model versions."
                max={6}
              />
            </div>
          </Panel>
          <Panel title="RECENT EVALUATIONS">
            <div className="panel-b tight">
              <DataTable
                cols={[
                  { key: "s", head: "SUBJECT", render: (r) => <span style={{ fontSize: 10.5 }}>{r.subject_ref}</span> },
                  { key: "v", head: "VERDICT", render: (r) => <Badge tone={toneFor(r.verdict)}>{r.verdict}</Badge> },
                ]}
                rows={evals}
                empty="No evaluations."
                max={5}
              />
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------- world */

export function WorldPage() {
  const [events, setEvents] = useState<GlobalEvent[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [regimes, setRegimes] = useState<Regime[] | null>(null);
  const [platform, setPlatform] = useState<PlatformEvent[] | null>(null);

  useEffect(() => {
    intelligenceApi.events().then((x) => setEvents(x.events)).catch(() => undefined);
    intelligenceApi.alerts().then((x) => setAlerts(x.alerts)).catch(() => undefined);
    intelligenceApi.regimes().then((x) => setRegimes(x.regimes)).catch(() => undefined);
    intelligenceApi.platformEvents(120).then((x) => setPlatform(x.events)).catch(() => undefined);
  }, []);

  const sevParts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of events ?? []) counts[e.severity || "info"] = (counts[e.severity || "info"] ?? 0) + 1;
    const color = (s: string) => (s === "high" ? "#ff5c69" : s === "medium" ? "#ffb454" : s === "low" ? "#4cc2ff" : "#5a6b84");
    return Object.entries(counts).map(([label, value]) => ({ label, value, color: color(label) }));
  }, [events]);

  return (
    <>
      <PageHead title="World" sub="Market context, global events, platform stream" />
      <div className="statrow">
        <Stat k="GLOBAL EVENTS" v={String(events?.length ?? 0)} />
        <Stat k="ALERTS" v={String(alerts?.length ?? 0)} />
        <Stat k="REGIMES" v={String(regimes?.length ?? 0)} />
        <Stat k="PLATFORM EVENTS" v={String(platform?.length ?? 0)} />
      </div>

      <div style={{ marginTop: 12 }}>
        <Panel title="EVENT SEVERITY MIX"><div className="panel-b"><DistBar parts={sevParts} /></div></Panel>
      </div>

      <div className="grid cols-2" style={{ marginTop: 12 }}>
        <Panel title="GLOBAL EVENTS" scroll tall>
          <div style={{ padding: "2px 0" }}>
            {(events ?? []).map((e, i) => (
              <div key={i} style={{ padding: "8px 12px", borderBottom: "1px solid var(--line-soft)" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Badge tone={e.severity === "high" ? "bad" : e.severity === "medium" ? "warn" : "dim"}>{e.severity || "info"}</Badge>
                  <span style={{ fontSize: 12 }}>{e.title}</span>
                  {e.symbol && <span className="sym" style={{ marginLeft: "auto" }}>{e.symbol}</span>}
                </div>
                <div className="tone-dim" style={{ fontSize: 10.5, marginTop: 2 }}>
                  {e.kind} · {fmt.ts(e.ts)}
                </div>
              </div>
            ))}
            {!events?.length && <Empty>No global events.</Empty>}
          </div>
        </Panel>
        <div style={{ display: "grid", gap: 12, alignContent: "start" }}>
          <Panel title="ALERTS" scroll>
            <DataTable
              cols={[
                { key: "s", head: "SEV", render: (r) => <Badge tone={r.severity === "high" ? "bad" : r.severity === "medium" ? "warn" : "dim"}>{r.severity}</Badge> },
                { key: "c", head: "CATEGORY", render: (r) => <span className="tone-dim">{r.category}</span> },
                { key: "m", head: "MESSAGE", render: (r) => <span style={{ fontSize: 11.5 }}>{r.message}</span> },
                { key: "t", head: "TIME", render: (r) => <span className="tone-dim">{fmt.ts(r.ts)}</span> },
              ]}
              rows={alerts}
              empty="No alerts."
            />
          </Panel>
          <Panel title="REGIMES" scroll>
            <DataTable
              cols={[
                { key: "s", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol}</span> },
                { key: "t", head: "TREND", render: (r) => <Badge tone={r.trend === "UP" ? "ok" : r.trend === "DOWN" ? "bad" : "dim"}>{r.trend}</Badge> },
                { key: "v", head: "VOL", render: (r) => <Badge tone={r.vol_regime === "HIGH" ? "warn" : "dim"}>{r.vol_regime}</Badge> },
                { key: "rv", head: "RVOL", num: true, render: (r) => fmt.pct(r.realized_vol_pct) },
              ]}
              rows={regimes}
              empty="No regime data."
            />
          </Panel>
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <Panel title="PLATFORM EVENT STREAM" scroll>
          <div style={{ padding: "2px 0", fontFamily: "var(--mono)", fontSize: 10.5 }}>
            {(platform ?? []).slice(0, 60).map((e, i) => (
              <div key={i} style={{ padding: "4px 12px", borderBottom: "1px solid var(--line-soft)", display: "flex", gap: 10 }}>
                <span className="tone-dim" style={{ width: 130, flexShrink: 0 }}>{fmt.ts(e.occurred_at ?? null)}</span>
                <span style={{ color: "var(--cyan)", width: 200, flexShrink: 0 }}>{e.kind}</span>
                <span className="tone-dim" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {JSON.stringify(e).slice(0, 140)}
                </span>
              </div>
            ))}
            {!platform?.length && <Empty>No platform events.</Empty>}
          </div>
        </Panel>
      </div>
    </>
  );
}
