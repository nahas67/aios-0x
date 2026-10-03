import React, { useState } from 'react';
import {
  FlaskConical,
  Activity,
  CheckCircle2,
  Play,
} from 'lucide-react';
import { portfolioApi, researchApi, type BacktestResult } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { adaptStrategies, type StrategyItemView } from '../../adapters/strategies';
import { Unavailable } from '../Unavailable';

/**
 * Strategies workspace: family rows from GET /api/v1/strategies, walk-forward
 * scoring from POST /api/v1/research/backtest over the live equity curve.
 * Sharpe / drawdown / capacity have no per-strategy source and render as "—";
 * no metric is ever computed client-side. The backtest POST is fail-closed
 * (401 without a bearer token) and says so honestly.
 */
export const StrategyResearchWorkspace: React.FC = () => {
  const strategiesQ = useApi(() => portfolioApi.strategies());
  const equityQ = useApi(() => portfolioApi.equity());

  const [selectedFamily, setSelectedFamily] = useState<string | null>(null);
  const [trainBars, setTrainBars] = useState<number>(90);
  const [testBars, setTestBars] = useState<number>(30);
  const [isScoring, setIsScoring] = useState<boolean>(false);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  if (strategiesQ.loading) {
    return <div className="text-xs text-text-muted font-mono p-8">Loading strategies from /api/v1/strategies…</div>;
  }
  if (strategiesQ.error || !strategiesQ.data) {
    return <Unavailable title="Strategies unavailable" reason={strategiesQ.error ?? "no strategies payload"} />;
  }
  const strategies: StrategyItemView[] = adaptStrategies(strategiesQ.data);
  const currentStrat = strategies.find(s => s.id === selectedFamily) || strategies[0] || null;

  const equityCloses: number[] | null =
    equityQ.data && Array.isArray(equityQ.data.equity) && equityQ.data.equity.length >= 3
      ? equityQ.data.equity.filter((v) => typeof v === "number" && Number.isFinite(v)).slice(-5000)
      : null;

  const handleRunBacktest = async () => {
    if (isScoring || !equityCloses) return;
    setIsScoring(true);
    setBacktest(null);
    setBacktestError(null);
    try {
      const result = await researchApi.backtest(equityCloses, trainBars, testBars);
      setBacktest(result);
      setNotification(`Walk-forward backtest complete: Sharpe ${result.sharpe ?? "—"}, max DD ${result.max_dd_pct ?? "—"}%`);
      setTimeout(() => setNotification(null), 4000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setBacktestError(
        msg.includes("401") || msg.toLowerCase().includes("authentication")
          ? "Operator token required: POST /api/v1/research/backtest answered 401. Set your bearer token and retry."
          : msg,
      );
    } finally {
      setIsScoring(false);
    }
  };

  const fmt = (v: number | null) => (v === null || v === undefined || Number.isNaN(v) ? "—" : String(v));

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              STRATEGY RESEARCH &amp; ALPHA LAB
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent font-bold">
              FRAME 9 &amp; 10
            </span>
          </div>
          <div className="text-xs text-text-muted mt-0.5">
            Source: /api/v1/strategies • Backtest: POST /api/v1/research/backtest over the live equity curve
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-surface-veil border border-border-subtle px-3 py-1.5 rounded">
            <span className="text-text-muted">ACTIVE FAMILIES:</span>{' '}
            <span className="text-text-strong font-bold">{strategies.filter(s => s.status === 'ACTIVE_PRODUCTION').length}</span>
          </div>
          <div className="bg-surface-veil border border-border-subtle px-3 py-1.5 rounded">
            <span className="text-text-muted">WEIGHTED SHARPE:</span>{' '}
            <span className="text-text-subtle font-bold">— (not computed)</span>
          </div>
        </div>
      </div>

      {notification && (
        <div className="p-3 rounded bg-positive-bg border border-positive text-positive text-xs flex items-center justify-between animate-fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-positive" />
            <span>{notification}</span>
          </div>
        </div>
      )}

      {strategies.length === 0 ? (
        <Unavailable
          title="No strategy families reported"
          reason="The backend returned an empty family list. Families appear once trials record realized PnL."
        />
      ) : (
        <>
          {/* Strategies Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {strategies.map((strat) => {
              const isSelected = currentStrat?.id === strat.id;
              const isProd = strat.status === 'ACTIVE_PRODUCTION';

              return (
                <div
                  key={strat.id}
                  onClick={() => setSelectedFamily(strat.id)}
                  className={`p-3.5 rounded-md cursor-pointer transition-all border ${
                    isSelected
                      ? 'bg-info-bg border-accent shadow-[0_0_16px_rgba(0,240,255,0.2)]'
                      : 'bg-[var(--color-surface-1)] border-border-strong hover:border-border-subtle hover:bg-surface-veil'
                  }`}
                >
                  <div className="flex items-center justify-between text-[10px] pb-2 border-b border-border-subtle">
                    <span className="text-accent font-bold">{strat.id}</span>
                    <span className={`px-1.5 py-0.2 rounded font-bold border ${
                      isProd ? 'bg-positive-bg text-positive border-positive' : 'bg-warning-bg text-warning border-warning'
                    }`}>
                      {strat.status}
                    </span>
                  </div>

                  <div className="mt-2">
                    <div className="font-bold text-text-strong text-xs leading-snug line-clamp-1">{strat.name}</div>
                    <div className="text-[10px] text-text-subtle mt-0.5">realized PnL ${strat.realizedPnl.toLocaleString()}</div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 mt-3 pt-2 border-t border-border-subtle text-[11px]">
                    <div>
                      <span className="text-[9px] text-text-subtle block">SHARPE</span>
                      <span className="text-text-subtle font-mono">—</span>
                    </div>
                    <div>
                      <span className="text-[9px] text-text-subtle block">MAX DD</span>
                      <span className="text-text-subtle font-mono">—</span>
                    </div>
                    <div>
                      <span className="text-[9px] text-text-subtle block">TRADES</span>
                      <span className="text-text-strong font-mono">{strat.tradesCount}</span>
                    </div>
                    <div>
                      <span className="text-[9px] text-text-subtle block">WIN RATE</span>
                      <span className="text-accent font-mono">{strat.winRatePct}%</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Server-side backtester */}
          <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl space-y-4">
            <div className="flex flex-wrap items-center justify-between pb-3 border-b border-border-subtle gap-2">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-accent" />
                <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
                  WALK-FORWARD BACKTEST — {currentStrat?.name ?? "—"}
                </h3>
              </div>
              <span className="text-[10px] text-text-muted">series: live equity curve ({equityCloses ? equityCloses.length : 0} points)</span>
            </div>

            <p className="text-xs text-text-muted bg-surface-sunken p-3 rounded border border-border-subtle leading-relaxed">
              Scoring runs server-side over the portfolio equity curve — no per-strategy price history is
              published, so results describe the book, not the selected family. Nothing is computed in the browser.
            </p>

            {/* Parameter Controls */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <div className="p-3 rounded bg-surface-veil border border-border-subtle space-y-1.5">
                <label className="text-[10px] text-text-muted uppercase tracking-wider block">
                  Train Bars
                </label>
                <input
                  type="number"
                  min={1}
                  value={trainBars}
                  onChange={(e) => setTrainBars(Math.max(1, Number(e.target.value) || 90))}
                  className="w-full bg-surface-deep border border-border-strong rounded px-2 py-1.5 text-text-strong font-mono"
                />
              </div>

              <div className="p-3 rounded bg-surface-veil border border-border-subtle space-y-1.5">
                <label className="text-[10px] text-text-muted uppercase tracking-wider block">
                  Test Bars
                </label>
                <input
                  type="number"
                  min={1}
                  value={testBars}
                  onChange={(e) => setTestBars(Math.max(1, Number(e.target.value) || 30))}
                  className="w-full bg-surface-deep border border-border-strong rounded px-2 py-1.5 text-text-strong font-mono"
                />
              </div>

              <div className="p-3 rounded bg-surface-veil border border-border-subtle space-y-1.5 flex flex-col justify-between">
                <div className="text-[10px] text-text-muted uppercase tracking-wider">
                  Server walk-forward
                </div>
                <button
                  onClick={handleRunBacktest}
                  disabled={isScoring || !equityCloses}
                  title={!equityCloses ? "No equity series available to score" : undefined}
                  className={`w-full py-1.5 rounded font-bold text-xs flex items-center justify-center gap-1.5 transition-all ${
                    isScoring
                      ? 'bg-info-bg text-accent border border-accent animate-pulse'
                      : 'bg-accent hover:bg-accent text-text-strong shadow-[0_0_12px_rgba(0,240,255,0.3)] disabled:opacity-40'
                  }`}
                >
                  {isScoring ? (
                    <>
                      <FlaskConical className="w-3.5 h-3.5 animate-spin" />
                      <span>SCORING SERVER-SIDE…</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5" />
                      <span>RUN SERVER BACKTEST</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {equityQ.error && (
              <div className="text-[11px] text-warning">
                Equity curve unavailable ({equityQ.error}) — the backtest has no series to score.
              </div>
            )}

            {backtestError && (
              <div className="p-3 rounded bg-destructive-bg border border-destructive text-destructive text-xs">
                {backtestError}
              </div>
            )}

            {/* Backtest Results (server-computed) */}
            {backtest && (
              <div className="p-4 rounded bg-info-bg border border-accent space-y-3 animate-fade-in">
                <div className="flex items-center justify-between pb-2 border-b border-accent">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-accent" />
                    <span className="font-bold text-xs text-text-strong uppercase tracking-wider">
                      SERVER WALK-FORWARD METRICS ({backtest.points} POINTS)
                    </span>
                  </div>
                  <span className="text-[10px] text-accent font-mono">
                    train {backtest.train_bars} / test {backtest.test_bars}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                  <div className="p-2.5 rounded bg-surface-sunken border border-border-strong">
                    <span className="text-[9px] text-text-muted block">SHARPE (FULL SERIES)</span>
                    <span className="text-lg font-bold text-positive font-mono">{fmt(backtest.sharpe)}</span>
                  </div>
                  <div className="p-2.5 rounded bg-surface-sunken border border-border-strong">
                    <span className="text-[9px] text-text-muted block">MAX DRAWDOWN %</span>
                    <span className="text-lg font-bold text-destructive font-mono">{fmt(backtest.max_dd_pct)}{backtest.max_dd_pct !== null ? '%' : ''}</span>
                  </div>
                  <div className="p-2.5 rounded bg-surface-sunken border border-border-strong">
                    <span className="text-[9px] text-text-muted block">WINDOWS</span>
                    <span className="text-lg font-bold text-text-strong font-mono">{backtest.windows.length}</span>
                  </div>
                </div>

                {backtest.windows.length > 0 && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-[11px]">
                      <thead className="text-[9px] uppercase text-text-subtle border-b border-border-subtle">
                        <tr>
                          <th className="py-1 pr-2">Window</th>
                          <th className="py-1 pr-2">Bars</th>
                          <th className="py-1 pr-2 text-right">Test Sharpe</th>
                          <th className="py-1 text-right">Test Max DD %</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-surface-veil">
                        {backtest.windows.slice(0, 20).map((w) => (
                          <tr key={w.window_index}>
                            <td className="py-1 pr-2 text-text font-mono">#{w.window_index}</td>
                            <td className="py-1 pr-2 text-text-muted font-mono">{w.start}–{w.end}</td>
                            <td className="py-1 pr-2 text-right text-positive font-mono">{fmt(w.test_sharpe)}</td>
                            <td className="py-1 text-right text-destructive font-mono">{fmt(w.test_max_dd_pct)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {backtest.windows.length > 20 && (
                      <div className="text-[10px] text-text-subtle pt-1">
                        Showing 20 of {backtest.windows.length} windows.
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/*
              REMOVED: "Promotion to production is not wired: no promotion endpoint exists."

              That was false, and it was false in the direction that hides capability. The
              endpoints exist -- POST /api/v1/control/promote_challenger and
              POST /api/v1/control/evaluate_trial, both RISK_ADMIN, dispatched by
              core/control_plane.py -- and they are wired: serve_command_center.py passes the
              single ControlPlane that ReplayRunner builds with both a challenge_registry and
              a trial_evaluator attached.

              An operator reading that note would have concluded the system could not promote a
              challenger, and would have had no reason to look for the control that does it.
              That is CONSTITUTION.md 3.1 as surely as the LIVE badge was: a claim about the
              system's own capability that the code contradicts.

              Promotion is not on this screen because it belongs to the trial it acts on, and a
              trial is not a backtest window. The Arena workspace (L25) owns it now, and it
              renders the recommendation, the evaluation verdict and the real preconditions
              rather than a claim that nothing exists.

              The sibling claims in this area were checked rather than assumed to share the
              defect: order submission, trim and flatten really do have no endpoint, so those
              notes stand.
            */}
          </div>
        </>
      )}
    </div>
  );
};
