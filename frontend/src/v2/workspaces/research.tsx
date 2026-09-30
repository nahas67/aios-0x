/**
 * RESEARCH workspaces — Knowledge (hypotheses + evidence), Calibration,
 * Decision Trace (hypothesis → evidence → verification → order → postmortem).
 *
 * The Decision Trace is the flagship explainability surface: every closed
 * trade can be opened as a chain from research to outcome.
 */
import { useEffect, useMemo, useState } from "react";
import {
  portfolioApi,
  researchApi,
  type CalibrationReport,
  type DecisionDrilldown,
  type Execution,
  type HypothesisDetail,
  type KnowledgeSummary,
} from "../api";
import { Badge, DataTable, Empty, fmt, PageHead, Panel, Stat, toneFor } from "../kit";

/* --------------------------------------------------------------- knowledge */

export function KnowledgePage() {
  const [k, setK] = useState<KnowledgeSummary | null>(null);
  const [sel, setSel] = useState<HypothesisDetail | null>(null);

  useEffect(() => {
    researchApi.knowledge().then(setK).catch(() => undefined);
  }, []);

  const open = (id: string) => {
    researchApi.hypothesis(id).then(setSel).catch(() => undefined);
  };

  const statusParts = useMemo(() => {
    const by = k?.by_status ?? {};
    const color = (s: string) =>
      s === "VALIDATED" ? "var(--ok)" : s === "REJECTED" || s === "REJECTED_HYPOTHESIS" ? "var(--bad)" : s === "TESTING" ? "var(--warn)" : "var(--cyan)";
    return Object.entries(by).map(([label, value]) => ({ label, value, color: color(label) }));
  }, [k]);

  return (
    <>
      <PageHead title="Knowledge" sub="Hypotheses, evidence ledgers, epistemic state" />
      <div className="statrow" style={{ marginBottom: 12 }}>
        <Stat k="HYPOTHESES" v={String(k?.total ?? 0)} />
        <Stat k="STATUSES" v={String(statusParts.length)} s="distinct states" />
      </div>

      {statusParts.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Panel title="STATUS DISTRIBUTION">
            <div className="panel-b">
              <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", background: "var(--panel-2)" }}>
                {statusParts.map((p) => (
                  <div key={p.label} style={{ width: `${(p.value / (k?.total || 1)) * 100}%`, background: p.color }} title={`${p.label}: ${p.value}`} />
                ))}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px", marginTop: 6 }}>
                {statusParts.map((p) => (
                  <span key={p.label} className="badge tone-dim">
                    <span className="dot" style={{ background: p.color, display: "inline-block", marginRight: 5 }} />
                    {p.label} {p.value}
                  </span>
                ))}
              </div>
            </div>
          </Panel>
        </div>
      )}

      <div className="grid cols-main">
        <Panel title="RECENT HYPOTHESES" scroll tall>
          <DataTable
            onRow={(r) => open(r.hypothesis_id)}
            selected={(r) => sel?.hypothesis_id === r.hypothesis_id}
            cols={[
              { key: "id", head: "ID", render: (r) => <span className="sym" style={{ fontSize: 10, fontWeight: 400 }}>{r.hypothesis_id.slice(0, 14)}…</span> },
              { key: "s", head: "STATEMENT", render: (r) => <span style={{ fontSize: 11.5 }}>{r.statement}</span> },
              { key: "sym", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
              { key: "st", head: "STATUS", render: (r) => <Badge tone={toneFor(r.status)}>{r.status}</Badge> },
              { key: "c", head: "CONF", num: true, render: (r) => fmt.pct(r.confidence != null ? r.confidence * 100 : null, 0) },
              { key: "e", head: "EVIDENCE", num: true, render: (r) => `${r.supports}↑ ${r.contradicts}↓` },
            ]}
            rows={k?.recent ?? null}
            empty="No hypotheses recorded."
          />
        </Panel>
        <Panel title="HYPOTHESIS DETAIL" scroll tall>
          {sel ? (
            <div style={{ padding: 12, display: "grid", gap: 10 }}>
              <div>
                <Badge tone={toneFor(sel.status)}>{sel.status}</Badge>{" "}
                <span className="sym" style={{ marginLeft: 6 }}>{sel.symbol ?? "—"}</span>{" "}
                <span className="tone-dim" style={{ fontSize: 11 }}>{sel.timeframe ?? ""}</span>
              </div>
              <div style={{ fontSize: 13 }}>{sel.statement}</div>
              {sel.rationale && (
                <div>
                  <div className="kv-label">RATIONALE</div>
                  <div className="tone-dim" style={{ fontSize: 12 }}>{sel.rationale}</div>
                </div>
              )}
              {sel.assumptions.length > 0 && (
                <div>
                  <div className="kv-label">ASSUMPTIONS</div>
                  {sel.assumptions.map((a, i) => (
                    <div key={i} style={{ fontSize: 12 }}>• {a}</div>
                  ))}
                </div>
              )}
              <div>
                <div className="kv-label">EVIDENCE ({sel.evidence.length})</div>
                {sel.evidence.length === 0 && <Empty>No evidence.</Empty>}
                {sel.evidence.map((e) => (
                  <div key={e.evidence_id} style={{ border: "1px solid var(--line-soft)", borderRadius: "var(--r)", padding: "7px 10px", marginBottom: 6 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <Badge tone={e.relationship === "SUPPORTS" ? "ok" : e.relationship === "CONTRADICTS" ? "bad" : "dim"}>{e.relationship}</Badge>
                      <span className="tone-dim" style={{ fontSize: 11 }}>{e.source}</span>
                      <span className="tone-dim" style={{ fontSize: 10, marginLeft: "auto" }}>{fmt.ts(e.retrieval_time)}</span>
                    </div>
                    {e.claims.map((c, i) => (
                      <div key={i} style={{ fontSize: 11.5, marginTop: 3 }}>+ {c}</div>
                    ))}
                    {e.counter_claims.map((c, i) => (
                      <div key={`x${i}`} style={{ fontSize: 11.5, marginTop: 3, color: "var(--bad)" }}>− {c}</div>
                    ))}
                  </div>
                ))}
              </div>
              <div className="tone-dim" style={{ fontSize: 10.5 }}>
                updated {fmt.ts(sel.last_updated)} · first seen {fmt.ts(sel.first_seen)}
              </div>
            </div>
          ) : (
            <Empty>Select a hypothesis to inspect its evidence ledger.</Empty>
          )}
        </Panel>
      </div>
    </>
  );
}

/* ------------------------------------------------------------- calibration */

export function CalibrationPage() {
  const [rep, setRep] = useState<CalibrationReport | null>(null);

  useEffect(() => {
    researchApi.research().then(setRep).catch(() => undefined);
  }, []);

  return (
    <>
      <PageHead title="Calibration" sub="Do predicted probabilities match observed outcomes?" />
      <div className="statrow" style={{ marginBottom: 12 }}>
        <Stat k="SCORED" v={String(rep?.total_scored ?? 0)} />
        <Stat k="BRIER SCORE" v={fmt.num(rep?.brier_score, 4)} s="lower is better" />
        <Stat k="DIRECTIONAL ACC" v={fmt.pct(rep?.directional_accuracy_pct, 1)} />
        <Stat k="RELIABLE" v={rep ? (rep.reliable ? "YES" : "NO") : "—"} tone={rep?.reliable ? "pos" : "warn"} />
      </div>

      <div className="grid cols-main">
        <Panel title="CALIBRATION BUCKETS — PREDICTED vs OBSERVED">
          <div className="panel-b">
            {rep?.buckets?.length ? (
              <table className="t">
                <thead>
                  <tr>
                    <th>BUCKET</th>
                    <th className="num">PREDICTED</th>
                    <th className="num">OBSERVED</th>
                    <th className="num">N</th>
                    <th style={{ width: "30%" }} />
                  </tr>
                </thead>
                <tbody>
                  {rep.buckets.map((b) => (
                    <tr key={b.bucket}>
                      <td className="mono">{b.bucket}</td>
                      <td className="num">{fmt.pct(b.predicted * 100, 0)}</td>
                      <td className="num">{fmt.pct(b.observed * 100, 0)}</td>
                      <td className="num">{b.count}</td>
                      <td>
                        <div style={{ position: "relative" }}>
                          <div className="bar-track" />
                          <div
                            style={{
                              position: "absolute",
                              left: 0,
                              top: 0,
                              height: 5,
                              borderRadius: 3,
                              width: `${Math.min(100, b.observed * 100)}%`,
                              background: "var(--ok)",
                            }}
                          />
                          <div
                            style={{
                              position: "absolute",
                              left: `${Math.min(100, b.predicted * 100)}%`,
                              top: -2,
                              height: 9,
                              width: 2,
                              background: "var(--amber)",
                            }}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Empty>No calibration data — predictions are scored postmortem.</Empty>
            )}
          </div>
        </Panel>
        <Panel title="READING THIS">
          <div className="panel-b tone-dim" style={{ fontSize: 12 }}>
            <p>Green bars = observed win rate per confidence bucket. The amber tick marks the predicted rate.</p>
            <p>When ticks align with bars, the institution's confidence is honest. A tick left of the bar means overconfidence — the research communities claim more certainty than outcomes justify.</p>
            <p>Brier score averages (predicted − outcome)². 0 is perfect, 0.25 is a coin flip.</p>
          </div>
        </Panel>
      </div>
    </>
  );
}

/* ----------------------------------------------------------- decision trace */

export function TracePage({ initialId }: { initialId?: string | null }) {
  const [execs, setExecs] = useState<Execution[] | null>(null);
  const [selId, setSelId] = useState<string | null>(initialId ?? null);
  const [trace, setTrace] = useState<DecisionDrilldown | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    portfolioApi.executions().then((x) => {
      setExecs(x.executions);
      if (!selId && x.executions.length) setSelId(x.executions[0].execution_id);
    }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selId) return;
    setTrace(null);
    setErr(null);
    researchApi.decisions(selId)
      .then(setTrace)
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
  }, [selId]);

  const sel = execs?.find((e) => e.execution_id === selId);

  return (
    <>
      <PageHead title="Decision Trace" sub="Hypothesis → evidence → verification → order → outcome — nothing hidden" />

      <div className="grid" style={{ gridTemplateColumns: "300px 1fr", gap: 12 }} >
        <Panel title="CLOSED TRADES" scroll tall>
          <DataTable
            onRow={(r) => setSelId(r.execution_id)}
            selected={(r) => r.execution_id === selId}
            cols={[
              { key: "s", head: "SYMBOL", render: (r) => <span className="sym">{r.symbol ?? "—"}</span> },
              { key: "p", head: "P&L", num: true, render: (r) => (
                <span style={{ color: r.realized_pnl >= 0 ? "var(--ok)" : "var(--bad)" }}>
                  {fmt.moneySigned(r.realized_pnl, 0)}
                </span>
              ) },
            ]}
            rows={execs}
            empty="No closed trades to trace."
          />
        </Panel>

        <div style={{ display: "grid", gap: 12, alignContent: "start", minWidth: 0 }}>
          {sel && (
            <div className="statrow">
              <Stat k="SYMBOL" v={sel.symbol ?? "—"} />
              <Stat k="ACTION" v={sel.action ?? "—"} />
              <Stat k="FILL" v={fmt.num(sel.fill_price, 2)} />
              <Stat k="REALIZED" v={fmt.moneySigned(sel.realized_pnl, 2)} tone={sel.realized_pnl >= 0 ? "pos" : "neg"} />
              <Stat k="CONFIDENCE" v={sel.confidence_pct != null ? `${sel.confidence_pct.toFixed(0)}%` : "—"} />
            </div>
          )}

          {err && <div className="severe">Decision trace unavailable: {err}</div>}

          {trace && (
            <Panel
              title="DECISION CHAIN"
              right={<Badge tone={trace.chain_complete ? "ok" : "warn"}>{trace.chain_complete ? "CHAIN COMPLETE" : "CHAIN INCOMPLETE"}</Badge>}
            >
              <div className="panel-b">
                <div className="stepper">
                  <Step n="1" title="HYPOTHESIS" tone={trace.decision.action ? "ok" : "warn"}>
                    <div style={{ fontSize: 13 }}>{trace.reason.thesis ?? "No thesis recorded."}</div>
                    <div className="tone-dim" style={{ fontSize: 11, marginTop: 4 }}>
                      {trace.decision.family ?? "—"} · size {fmt.pct(trace.decision.position_size_pct, 2)}
                    </div>
                  </Step>
                  <Step n="2" title="EVIDENCE" tone={trace.evidence.supporting_arguments.length ? "ok" : "warn"}>
                    {trace.evidence.supporting_arguments.map((a, i) => (
                      <div key={i} style={{ fontSize: 12 }}>+ {a}</div>
                    ))}
                    {trace.evidence.counter_arguments.map((a, i) => (
                      <div key={`c${i}`} style={{ fontSize: 12, color: "var(--bad)" }}>− {a}</div>
                    ))}
                    {!trace.evidence.supporting_arguments.length && !trace.evidence.counter_arguments.length && (
                      <span className="tone-dim" style={{ fontSize: 12 }}>No evidence recorded.</span>
                    )}
                  </Step>
                  <Step n="3" title="VERIFICATION" tone={trace.verification.flagged_hallucinations.length ? "bad" : "ok"}>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <Badge tone="info">confidence {fmt.pct(trace.verification.confidence_score != null ? trace.verification.confidence_score * 100 : null, 0)}</Badge>
                      <Badge tone="ok">fact {fmt.pct(trace.verification.fact_score != null ? trace.verification.fact_score * 100 : null, 0)}</Badge>
                      <Badge tone="info">balance {fmt.pct(trace.verification.balance_score != null ? trace.verification.balance_score * 100 : null, 0)}</Badge>
                      <Badge tone="ok">math {fmt.pct(trace.verification.math_score != null ? trace.verification.math_score * 100 : null, 0)}</Badge>
                    </div>
                    {trace.verification.flagged_hallucinations.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        <Badge tone="bad">🚨 {trace.verification.flagged_hallucinations.length} FLAGGED</Badge>
                        {trace.verification.flagged_hallucinations.map((h, i) => (
                          <div key={i} style={{ fontSize: 11.5, color: "var(--bad)", marginTop: 3 }}>• {h}</div>
                        ))}
                      </div>
                    )}
                    {trace.verification.flagged_hallucinations.length === 0 && (
                      <div className="tone-dim" style={{ fontSize: 11.5, marginTop: 6 }}>C3 verification firewall found no hallucinations.</div>
                    )}
                  </Step>
                  <Step n="4" title="RISK ENVELOPE" tone={trace.risk.stop_loss_price != null ? "ok" : "warn"}>
                    <div className="mono" style={{ fontSize: 12 }}>
                      stop {fmt.num(trace.risk.stop_loss_price, 2)} · target {fmt.num(trace.risk.take_profit_price, 2)}
                    </div>
                  </Step>
                  <Step n="5" title="OUTCOME" tone={trace.outcome.actual_pnl != null ? (trace.outcome.actual_pnl >= 0 ? "ok" : "bad") : "warn"}>
                    {trace.outcome.actual_pnl != null && (
                      <div className="mono" style={{ fontSize: 13, color: trace.outcome.actual_pnl >= 0 ? "var(--ok)" : "var(--bad)" }}>
                        {fmt.moneySigned(trace.outcome.actual_pnl, 2)}
                      </div>
                    )}
                    <div className="tone-dim" style={{ fontSize: 11.5 }}>
                      exit: {trace.outcome.exit_reason ?? "—"} · direction {trace.outcome.direction_correct == null ? "—" : trace.outcome.direction_correct ? "correct" : "wrong"}
                    </div>
                    {trace.outcome.lessons_learned.map((l, i) => (
                      <div key={i} style={{ fontSize: 11.5, marginTop: 3 }}>📌 {l}</div>
                    ))}
                  </Step>
                </div>
              </div>
            </Panel>
          )}

          {!trace && !err && selId && <Panel title="DECISION CHAIN"><div className="panel-b"><Empty>Loading trace…</Empty></div></Panel>}
        </div>
      </div>
    </>
  );
}

function Step({
  n,
  title,
  tone,
  children,
}: {
  n: string;
  title: string;
  tone: "ok" | "bad" | "warn";
  children: React.ReactNode;
}) {
  return (
    <div className="step">
      <div className={`step-dot ${tone}`}>{tone === "ok" ? "✓" : tone === "bad" ? "✕" : "!"}</div>
      <div className="step-title">{n} · {title}</div>
      <div className="step-body">{children}</div>
    </div>
  );
}
