import { useState } from "react";
import { modelsApi, researchApi } from "../../api/endpoints";
import type { HypothesisDetail } from "../../api/types";
import { DataTable, Empty, ErrorBox, KV, Modal, Panel, Pill } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDateTime, fmtNum, fmtPct } from "../../lib/format";
import { statusTone } from "../../lib/format";

export function KnowledgePage() {
  const knowledge = useApi(() => researchApi.knowledge());
  const [openId, setOpenId] = useState<string | null>(null);
  const k = knowledge.data;

  return (
    <>
      <div className="pagehead">
        <h1>Hypotheses & Knowledge</h1>
        <span className="sub">Durable research memory with evidence graphs</span>
      </div>
      {knowledge.error ? (
        <ErrorBox title="Knowledge unavailable" detail={knowledge.error} />
      ) : !k?.available ? (
        <Panel title="Research Plane">
          <Empty>Research engine not wired in this run — start with the research plane enabled.</Empty>
        </Panel>
      ) : (
        <>
          <div className="grid cols-4" style={{ marginBottom: "var(--gap)" }}>
            {Object.entries(k.by_status ?? {}).map(([status, count]) => (
              <Panel key={status}>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{fmtNum(count)}</div>
                <div className="dim" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>{status}</div>
              </Panel>
            ))}
          </div>
          <Panel title={`Hypotheses${k.recent ? ` (${k.recent.length})` : ""}`}>
            <DataTable
              rows={k.recent}
              rowKey={(r) => r.hypothesis_id}
              onRowClick={(r) => setOpenId(r.hypothesis_id)}
              empty="No hypotheses recorded yet."
              columns={[
                { key: "statement", label: "Statement", render: (r) => <span>{r.statement}</span> },
                { key: "symbol", label: "Symbol", render: (r) => (r.symbol ? <span className="sym">{r.symbol}</span> : <span className="faint">—</span>) },
                { key: "status", label: "Status", render: (r) => <Pill tone={statusTone(r.status)}>{r.status}</Pill> },
                { key: "confidence", label: "Conf", numeric: true, render: (r) => (r.confidence !== null ? fmtPct(r.confidence * 100) : "—") },
                { key: "evidence_total", label: "Evidence", numeric: true },
                { key: "supports", label: "✓", numeric: true },
                { key: "contradicts", label: "✗", numeric: true },
                { key: "last_updated", label: "Updated", render: (r) => <span className="dim">{fmtDateTime(r.last_updated)}</span> },
              ]}
            />
          </Panel>
          {openId && <HypothesisModal id={openId} onClose={() => setOpenId(null)} />}
        </>
      )}
    </>
  );
}

function HypothesisModal({ id, onClose }: { id: string; onClose: () => void }) {
  const detail = useApi(() => researchApi.hypothesis(id));
  const d = detail.data as HypothesisDetail | null;
  return (
    <Modal title="Hypothesis Detail" onClose={onClose} width={640}>
      {detail.loading && <p className="dim">Loading…</p>}
      {detail.error && <ErrorBox title="Load failed" detail={detail.error} />}
      {d && (
        <>
          <div className="chips" style={{ marginBottom: 8 }}>
            <Pill tone={statusTone(d.status)}>{d.status}</Pill>
            {d.symbol && <span className="chip">{d.symbol}</span>}
            {d.timeframe && <span className="chip">{d.timeframe}</span>}
            {d.confidence !== null && <span className="chip">conf {fmtPct(d.confidence * 100)}</span>}
          </div>
          <p style={{ marginTop: 0, fontSize: 13.5 }}>{d.statement}</p>
          {d.rationale && <p className="dim" style={{ fontSize: 12.5 }}>{d.rationale}</p>}
          <KV k="Expected outcome" v={d.expected_outcome ?? "—"} />
          <KV k="Risk:reward" v={d.expected_risk_reward_ratio !== null ? String(d.expected_risk_reward_ratio) : "—"} />
          <KV k="First seen" v={fmtDateTime(d.first_seen)} />
          <KV k="Last updated" v={fmtDateTime(d.last_updated)} />
          <div className="dim" style={{ margin: "12px 0 4px", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Evidence graph ({d.evidence.length})
          </div>
          {d.evidence.length === 0 ? (
            <Empty>No evidence linked yet.</Empty>
          ) : (
            d.evidence.slice(0, 8).map((e) => (
              <div key={e.evidence_id} style={{ borderBottom: "1px solid var(--hairline)", padding: "6px 0", fontSize: 12.5 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Pill tone={e.relationship === "supports" ? "ok" : e.relationship === "contradicts" ? "bad" : "info"}>{e.relationship}</Pill>
                  <span className="dim">{e.source}</span>
                  {e.confidence !== null && <span className="faint" style={{ fontSize: 11 }}>conf {fmtPct(e.confidence * 100)}</span>}
                </div>
                {e.claims.slice(0, 2).map((c, i) => (
                  <div key={i} style={{ marginTop: 2 }}>• {c}</div>
                ))}
              </div>
            ))
          )}
        </>
      )}
    </Modal>
  );
}

export function ModelsPage() {
  const models = useApi(() => modelsApi.models());
  const evals = useApi(() => modelsApi.evaluations());
  const m = models.data;

  return (
    <>
      <div className="pagehead">
        <h1>Models</h1>
        <span className="sub">Model registry + lifecycle (§12) + walk-forward evaluation records</span>
      </div>
      {models.error ? (
        <ErrorBox title="Models unavailable" detail={models.error} />
      ) : !m?.available ? (
        <Panel title="Model Registry">
          <Empty>Kernel bridge not wired in this run — model lifecycle unavailable.</Empty>
        </Panel>
      ) : (
        <>
          <Panel title={`Registered Models (${m.models.length})`}>
            <DataTable
              rows={m.models}
              rowKey={(r) => `${r.model_id}@${r.version}`}
              empty="No models registered."
              columns={[
                { key: "model_id", label: "Model", render: (r) => <span className="sym">{r.model_id}</span> },
                { key: "version", label: "Version", render: (r) => <span className="mono">{r.version}</span> },
                { key: "status", label: "Status", render: (r) => <Pill tone={statusTone(r.status)}>{r.status}</Pill> },
                { key: "artifact_hash", label: "Artifact", render: (r) => <span className="mono faint">{r.artifact_hash ? String(r.artifact_hash).slice(0, 12) + "…" : "—"}</span> },
                {
                  key: "walk_forward",
                  label: "Walk-forward",
                  render: (r) =>
                    r.walk_forward ? (
                      <span className="dim">{Object.entries(r.walk_forward).slice(0, 3).map(([k, v]) => `${k}=${String(v)}`).join("  ")}</span>
                    ) : (
                      <span className="faint">—</span>
                    ),
                },
              ]}
            />
          </Panel>
          <Panel title={`Evaluation Records (${evals.data?.evaluations?.length ?? 0})`}>
            <DataTable
              rows={evals.data?.evaluations}
              rowKey={(r) => r.evaluation_id}
              empty="No evaluation records."
              columns={[
                { key: "created_at", label: "Time", render: (r) => <span className="dim">{fmtDateTime(r.created_at)}</span> },
                { key: "subject_ref", label: "Subject", render: (r) => <span className="mono">{r.subject_ref}</span> },
                { key: "evaluator", label: "Evaluator", render: (r) => <span className="dim">{r.evaluator}</span> },
                { key: "verdict", label: "Verdict", render: (r) => <Pill tone={statusTone(r.verdict)}>{r.verdict}</Pill> },
                { key: "summary", label: "Summary" },
              ]}
            />
          </Panel>
        </>
      )}
    </>
  );
}

export function ResearchQualityPage() {
  const report = useApi(() => researchApi.research());
  const r = report.data;

  return (
    <>
      <div className="pagehead">
        <h1>Research Quality</h1>
        <span className="sub">Prediction-ledger calibration — how honest the engine's confidence is</span>
      </div>
      {report.error ? (
        <ErrorBox title="Calibration unavailable" detail={report.error} />
      ) : !r ? (
        <Panel title="Calibration">
          <Empty>Loading…</Empty>
        </Panel>
      ) : (
        <>
          <div className="grid cols-4" style={{ marginBottom: "var(--gap)" }}>
            <Panel>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{fmtNum(r.total_scored)}</div>
              <div className="dim" style={{ fontSize: 11 }}>scored predictions</div>
            </Panel>
            <Panel>
              <div style={{ fontSize: 22, fontWeight: 700, color: r.brier_score <= 0.25 ? "var(--ok)" : "var(--warn)" }}>{r.brier_score.toFixed(3)}</div>
              <div className="dim" style={{ fontSize: 11 }}>Brier score (lower is better)</div>
            </Panel>
            <Panel>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{fmtPct(r.directional_accuracy_pct)}</div>
              <div className="dim" style={{ fontSize: 11 }}>directional accuracy</div>
            </Panel>
            <Panel>
              <div style={{ fontSize: 22, fontWeight: 700 }}>
                <Pill tone={r.reliable ? "ok" : "warn"}>{r.reliable ? "RELIABLE" : "LOW SAMPLE"}</Pill>
              </div>
              <div className="dim" style={{ fontSize: 11 }}>{r.reliable ? "≥20 scored predictions" : "below 20 — do not judge yet"}</div>
            </Panel>
          </div>
          <Panel title="Reliability by Confidence Bucket">
            <DataTable
              rows={r.buckets}
              rowKey={(b) => b.bucket}
              empty="No scored predictions yet — buckets fill as outcomes settle."
              columns={[
                { key: "bucket", label: "Bucket" },
                { key: "count", label: "N", numeric: true },
                { key: "predicted", label: "Predicted", numeric: true, render: (b) => fmtPct(b.predicted * 100) },
                { key: "observed", label: "Observed", numeric: true, render: (b) => fmtPct(b.observed * 100) },
                {
                  key: "gap",
                  label: "Calibration gap",
                  numeric: true,
                  render: (b) => {
                    const gap = Math.abs(b.predicted - b.observed) * 100;
                    return <Pill tone={gap <= 10 ? "ok" : gap <= 25 ? "warn" : "bad"}>{gap.toFixed(1)}pp</Pill>;
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

export function MemoryPage() {
  const memory = useApi(() => researchApi.memory());
  const m = memory.data as { counts?: Record<string, number>; lesson_samples?: { execution_id: string; lesson: string; exit_reason: string }[]; note?: string } | null;

  return (
    <>
      <div className="pagehead">
        <h1>Research Memory</h1>
        <span className="sub">Immutable raw log + lesson summaries that reference evidence ids</span>
      </div>
      {memory.error ? (
        <ErrorBox title="Memory unavailable" detail={memory.error} />
      ) : (
        <div className="grid cols-2">
          <Panel title="Store Counts">
            {m?.counts
              ? Object.entries(m.counts).map(([k, v]) => <KV key={k} k={k} v={fmtNum(v)} />)
              : <Empty>Loading…</Empty>}
          </Panel>
          <Panel title="Recent Lessons">
            {m?.lesson_samples?.length ? (
              m.lesson_samples.map((l, i) => (
                <div key={i} style={{ borderBottom: "1px solid var(--hairline)", padding: "6px 0", fontSize: 12.5 }}>
                  <span className="mono faint" style={{ fontSize: 10.5 }}>{l.execution_id.slice(0, 10)}…</span>
                  <Pill tone={l.exit_reason === "STOP_LOSS" ? "bad" : "dim"}>{l.exit_reason}</Pill>
                  <div style={{ marginTop: 2 }}>{l.lesson}</div>
                </div>
              ))
            ) : (
              <Empty>No lessons recorded yet.</Empty>
            )}
          </Panel>
        </div>
      )}
    </>
  );
}
