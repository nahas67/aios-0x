import React, { useState } from 'react';
import {
  Ban,
  CheckCircle2,
  FlaskConical,
  PlugZap,
  Swords,
  Trophy,
  XCircle,
} from 'lucide-react';
import { arenaApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { useStreamRefresh } from '../../hooks/useStreamRefresh';
import { adaptArena, kernelBlocker, type AdaptedArenaTrial } from '../../adapters/arena';
import { ControlFailure, runControl } from '../../lib/control';
import { classifyList, describe } from '../../lib/stateView';
import { fmtDateTime, fmtNum, fmtPct, fmtUsd } from '../../lib/format';
import { StateView } from '../StateView';
import { Unavailable } from '../Unavailable';

/**
 * Named so the empty state can say who looked. Every `classifyList` call in this file
 * attributes its result to this string, which is what stops "the registry holds no
 * trials" from being rendered by a view that never learned whether it could ask.
 */
const ARENA_SOURCE = '/api/v1/arena';

/** Per-trial action feedback. Never cleared optimistically — only after the server answers. */
interface ActionReport {
  ok: boolean;
  text: string;
}

/**
 * Layer 25 — the CHAMPION/CHALLENGER ARENA, as a screen.
 *
 * WHY THIS VIEW HAD TO EXIST. The endpoint, the promotion gate and both control actions
 * were already implemented and tested, and nothing rendered them. `promote_challenger`
 * was an action in the catalog with no surface to press it from — the terminus of §12's
 * chain (`Memory → Counterfactual evaluation → Champion/Challenger`) was reachable from
 * no page.
 *
 * FOUR FACTS THIS VIEW IS NOT ALLOWED TO SMOOTH OVER
 * ====================================================
 *
 * 1. `wired: false` IS A WIRING FACT, NOT AN EMPTY ARENA. The server answered 200 and
 *    reported `trials: []` because no ChallengeRegistry is attached to the composition
 *    root. Rendering that through the same empty state as a registry that genuinely
 *    holds nothing would claim an operator asked and was told the arena is empty —
 *    which nobody did. So `wired` gets its own panel, and the trial list is not rendered
 *    at all in that case.
 *
 * 2. `INSUFFICIENT_EVIDENCE` IS NOT A RESULT. `ChallengerTrial.recommend()` returns it
 *    with no metric, no margin and no comparison until BOTH sides have been run. It is
 *    shown as a distinct state with the two per-side figures marked as not yet run. It
 *    is never rendered as zero, as a tie, or as a loss — a trial that was never run has
 *    not lost.
 *
 * 3. `verdict: null` MEANS THERE IS NO EvaluationRecord, AND PROMOTION IS REFUSED
 *    WITHOUT ONE. The adapter names that blocker, the button is disabled, and the reason
 *    is written next to it. The same applies to a non-PASS verdict and to `kernel_wired:
 *    false` (no promotion/rollback controllers — the control plane will refuse).
 *
 * 4. `PROMOTED` IS TERMINAL. No demote, no toggle back, no "revert" affordance appears
 *    for a promoted trial. Reversal is a governance question this release does not
 *    answer, and a button that looked like an undo would be the worst possible answer.
 *
 * NO CLIENT-SIDE AUTHORITY
 * =======================
 * `evaluate_trial` and `promote_challenger` both go through `runControl`, which POSTs to
 * the control plane where the server resolves identity and role. The buttons here are
 * disabled by preconditions the server also enforces — never as a substitute for it. And
 * nothing local is mutated on click: this view holds no trial state of its own and
 * re-reads the arena from the server after every accepted action, so a refusal cannot
 * leave a promoted-looking trial on screen. A denial (403 / insufficient role) is shown
 * verbatim.
 */
export const ArenaWorkspace: React.FC = () => {
  // Trial states change on a control action rather than on a tick, so a long stream
  // interval keeps this cheap; the explicit `refresh()` after each action is what
  // re-reads the arena. Stream-driven anyway so a promotion recorded elsewhere shows up.
  const tick = useStreamRefresh(15_000);
  const arenaQ = useApi(() => arenaApi.arena(), [tick]);

  const [busy, setBusy] = useState<string | null>(null);
  const [report, setReport] = useState<Record<string, ActionReport>>({});

  if (arenaQ.loading) {
    return (
      <div className="text-xs text-text-muted font-mono p-8">
        Loading champion/challenger trials from /api/v1/arena…
      </div>
    );
  }
  if (arenaQ.error || !arenaQ.data) {
    return (
      <Unavailable
        title="Arena unavailable"
        reason={arenaQ.error ?? 'no arena payload'}
      />
    );
  }

  const adapted = adaptArena(arenaQ.data);
  if ('unavailable' in adapted) {
    return <Unavailable title="Arena unavailable" reason={adapted.unavailable} />;
  }

  const arena = adapted;
  const kernelReason = kernelBlocker(arena.kernelWired);
  const trialState = classifyList(arena.trials, ARENA_SOURCE);
  // Mutable, and keyed off the trial union rather than a hand-written list: a state the
  // backend adds must fail to type-check here rather than be silently uncounted.
  const stateCounts: Record<AdaptedArenaTrial['state'], number> = {
    PROPOSED: 0,
    EVALUATED: 0,
    PROMOTED: 0,
    REJECTED: 0,
  };
  for (const trial of arena.trials) {
    stateCounts[trial.state] += 1;
  }

  /**
   * One audited control action, then re-read from the server. Nothing is assumed to have
   * succeeded: on success the arena is refetched so the rendered state is the server's,
   * and on failure the server's own text is shown.
   */
  const run = async (
    trial: AdaptedArenaTrial,
    action: 'evaluate_trial' | 'promote_challenger',
    params: Record<string, string>,
  ) => {
    if (busy) return;
    setBusy(`${action}:${trial.name}`);
    setReport((prev) => {
      const { [trial.name]: _dropped, ...rest } = prev;
      return rest;
    });
    try {
      const result = await runControl(action, params);
      setReport((prev) => ({
        ...prev,
        [trial.name]: {
          ok: true,
          text:
            result.authorized === true
              ? `${action} accepted by the control plane for ${trial.name}. Re-reading /api/v1/arena.`
              : `${action} answered authorized=false for ${trial.name}. Re-reading /api/v1/arena.`,
        },
      }));
      arenaQ.refresh();
    } catch (err) {
      const message = err instanceof ControlFailure ? err.message : String(err);
      setReport((prev) => ({
        ...prev,
        [trial.name]: {
          ok: false,
          text:
            err instanceof ControlFailure && err.kind === 'denied'
              ? `${action} denied: ${message} — this role may not perform it, and no client-side override exists.`
              : `${action} failed: ${message}`,
        },
      }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <Swords className="w-4 h-4 text-accent" />
          <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
            LAYER 25 · CHAMPION / CHALLENGER ARENA
          </h2>
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
            §12 TERMINUS
          </span>
        </div>
        <div className="flex items-center gap-2">
          <WiringBadge wired={arena.wired} />
          <KernelBadge wired={arena.kernelWired} />
        </div>
      </div>

      {/* FACT 1: unwired is not empty. This panel replaces the trial list entirely. */}
      {!arena.wired && (
        <div className="bg-[var(--color-surface-1)] border border-warning rounded-md p-4">
          <div className="flex items-center gap-2">
            <PlugZap className="w-4 h-4 text-warning" />
            <h3 className="text-[11px] font-bold tracking-wider text-warning uppercase">
              ARENA NOT WIRED
            </h3>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-text-muted">{arena.note}</p>
          <p className="mt-2 text-[10px] text-text-subtle leading-relaxed">
            This is a statement about this deployment&apos;s composition root, not about
            whether any trial exists. No trial count is shown, because no one asked.
          </p>
        </div>
      )}

      {arena.wired && (
        <>
          {/* Counts by state, straight from the payload. */}
          <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
              <div className="flex items-center gap-2">
                <FlaskConical className="w-4 h-4 text-accent" />
                <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
                  TRIAL STATES (BACKEND-REPORTED)
                </h3>
              </div>
              <span className="text-[10px] text-accent font-bold">
                {arena.trials.length} TRIALS REGISTERED
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-3 text-xs">
              {(Object.keys(stateCounts) as AdaptedArenaTrial['state'][]).map((state) => (
                <div
                  key={state}
                  className="p-2.5 rounded bg-surface-veil border border-border-subtle text-center"
                >
                  <div className="text-[9px] text-text-subtle uppercase">{state}</div>
                  <div className="text-base font-mono-num font-bold text-text-strong">
                    {stateCounts[state]}
                  </div>
                </div>
              ))}
            </div>

            <p className="mt-3 text-[11px] leading-relaxed text-text-muted border-t border-border-subtle pt-3">
              {arena.note}
            </p>
          </div>

          {/* Promotion readiness, stated before the button is pressed. */}
          {kernelReason && (
            <div className="bg-[var(--color-surface-1)] border border-warning rounded-md p-4">
              <div className="flex items-center gap-2">
                <Ban className="w-4 h-4 text-warning" />
                <h3 className="text-[11px] font-bold tracking-wider text-warning uppercase">
                  PROMOTION WILL BE REFUSED
                </h3>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-text-muted">
                {kernelReason}. Promote and reject are disabled below. This is a
                composition-root fact, not a verdict on any trial.
              </p>
            </div>
          )}

          {/* Trials, or the classified empty state. Never a hand-rolled caption. */}
          <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md overflow-hidden">
            <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
              <h3 className="text-[11px] font-bold tracking-wider text-text uppercase">
                TRIALS
              </h3>
              <span className="text-[9px] text-text-subtle">
                a recommendation is evidence, not a decision
              </span>
            </div>

            <StateView state={trialState} noun="champion/challenger trials" />

            {trialState.kind === 'ready' && (
              <div className="divide-y divide-border-subtle">
                {arena.trials.map((trial) => (
                  <TrialCard
                    key={trial.name}
                    trial={trial}
                    busy={busy}
                    kernelWired={arena.kernelWired}
                    report={report[trial.name]}
                    onEvaluate={() => void run(trial, 'evaluate_trial', { name: trial.name })}
                    onPromote={() =>
                      void run(trial, 'promote_challenger', {
                        trial_name: trial.name,
                        decision: 'promote',
                      })
                    }
                    onReject={() =>
                      void run(trial, 'promote_challenger', {
                        trial_name: trial.name,
                        decision: 'reject',
                      })
                    }
                  />
                ))}
              </div>
            )}
          </div>

          {trialState.kind === 'empty' && (
            <p className="text-[10px] text-text-subtle font-mono">{describe(trialState, 'champion/challenger trials')}</p>
          )}
        </>
      )}
    </div>
  );
};

// ------------------------------------------------------------------ trial card

function TrialCard({
  trial,
  busy,
  kernelWired,
  report,
  onEvaluate,
  onPromote,
  onReject,
}: {
  trial: AdaptedArenaTrial;
  busy: string | null;
  kernelWired: boolean;
  report: ActionReport | undefined;
  onEvaluate: () => void;
  onPromote: () => void;
  onReject: () => void;
}) {
  const isBusy = (action: string) => busy === `${action}:${trial.name}`;
  const promotionBlocked = trial.promotionBlockedReason ?? (kernelWired ? null : 'promotion controllers are not wired on this deployment');
  const promoteDisabled = !trial.promotionPreconditionsMet || !kernelWired || busy !== null;

  return (
    <article className="p-4 space-y-3">
      {/* Identity */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-text-strong break-all">{trial.name}</span>
            <StateBadge state={trial.state} />
          </div>
          {trial.description && (
            <p className="mt-1 text-[11px] text-text-muted leading-relaxed">{trial.description}</p>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-text-subtle">
            <span>
              metric:{' '}
              <span className="text-text-muted font-mono">{trial.metric}</span>
            </span>
            <span>
              evaluated:{' '}
              <span className="text-text-muted font-mono">{fmtDateTime(trial.evaluatedAt)}</span>
            </span>
            {trial.promotedBy && (
              <span>
                promoted by:{' '}
                <span className="text-text-muted font-mono">{trial.promotedBy}</span>
              </span>
            )}
          </div>
        </div>
        <RecommendationBadge recommendation={trial.recommendation} />
      </div>

      {/* Champion vs challenger. A side that was never run reads "NOT RUN", not "0". */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <SideTable label="CHAMPION" side={trial.champion} />
        <SideTable label="CHALLENGER" side={trial.challenger} />
      </div>

      {/* The comparison the recommendation is based on, or the reason there is none. */}
      <div className="bg-surface-veil border border-border-subtle rounded p-3 text-[10px]">
        {trial.recommendation.insufficientEvidence ? (
          <div className="space-y-1">
            <div className="font-bold text-warning">
              INSUFFICIENT_EVIDENCE — the trial has not been run on both sides.
            </div>
            <p className="text-text-muted leading-relaxed">
              No comparison exists yet, so no margin and no metric figure can be reported.
              This is not a loss and not a tie: it is an absence of runs.{' '}
              {trial.champion === null && 'The champion side has not been run. '}
              {trial.challenger === null && 'The challenger side has not been run.'}
            </p>
            {trial.recommendation.note && (
              <p className="text-text-subtle leading-relaxed">{trial.recommendation.note}</p>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="text-text-subtle">
              on metric{' '}
              <span className="text-text-muted font-mono">
                {trial.recommendation.metric ?? trial.metric}
              </span>
            </span>
            <span className="text-text-subtle">
              champion <span className="text-text-strong font-mono">{fmtNum(trial.recommendation.champion)}</span>
            </span>
            <span className="text-text-subtle">
              challenger{' '}
              <span className="text-text-strong font-mono">{fmtNum(trial.recommendation.challenger)}</span>
            </span>
            <span className="text-text-subtle">
              margin <span className="text-text-strong font-mono">{fmtNum(trial.recommendation.margin)}</span>
            </span>
            {trial.recommendation.note && (
              <span className="text-text-subtle">{trial.recommendation.note}</span>
            )}
          </div>
        )}
      </div>

      {/* The EvaluationRecord, when one exists. Absent is shown as absent. */}
      <div className="bg-surface-veil border border-border-subtle rounded p-3 text-[10px]">
        {trial.verdict ? (
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-text-subtle uppercase">evaluation record</span>
              <span
                className={`px-1.5 py-0.5 rounded border font-bold ${
                  trial.verdict.verdict.toUpperCase() === 'PASS'
                    ? 'bg-positive-bg text-positive border-positive'
                    : 'bg-warning-bg text-warning border-warning'
                }`}
              >
                {trial.verdict.verdict}
              </span>
              <span className="text-text-subtle font-mono">{trial.verdict.evaluation_id}</span>
              <span className="text-text-subtle">by {trial.verdict.evaluator}</span>
              <span className="text-text-subtle font-mono">{fmtDateTime(trial.verdict.created_at)}</span>
            </div>
            <p className="text-text-muted leading-relaxed">{trial.verdict.summary}</p>
          </div>
        ) : (
          <div className="space-y-1">
            <div className="font-bold text-warning">NO EVALUATION RECORD ON THIS TRIAL</div>
            <p className="text-text-muted leading-relaxed">
              Promotion is refused without one. Evaluating produces evidence only — it is
              not a decision, and it does not promote anything.
            </p>
          </div>
        )}
      </div>

      {/* Notes, verbatim from the registry. */}
      {trial.notes.length > 0 && (
        <ul className="text-[10px] text-text-muted space-y-1 list-disc list-inside">
          {trial.notes.map((note) => (
            <li key={note} className="leading-relaxed">
              {note}
            </li>
          ))}
        </ul>
      )}

      {/* Server outcome of the last action, verbatim. */}
      {report && (
        <div
          role="status"
          className={`text-[10px] leading-relaxed rounded border p-2.5 ${
            report.ok
              ? 'bg-positive-bg text-positive border-positive'
              : 'bg-destructive-bg text-destructive border-destructive'
          }`}
        >
          {report.text}
        </div>
      )}

      {/* Controls. Every one goes through runControl — the server is the only authority. */}
      <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border-subtle">
        <button
          onClick={onEvaluate}
          disabled={busy !== null}
          className={`px-3 py-1.5 rounded text-[11px] font-bold border transition-colors flex items-center gap-1.5 ${
            busy !== null
              ? 'bg-surface-veil text-text-subtle border-border-subtle cursor-not-allowed'
              : 'bg-info-bg text-accent border-accent hover:bg-surface-raised'
          }`}
        >
          <FlaskConical className="w-3.5 h-3.5" />
          <span>{isBusy('evaluate_trial') ? 'EVALUATING…' : 'EVALUATE TRIAL'}</span>
        </button>

        <button
          onClick={onPromote}
          disabled={promoteDisabled}
          title={promotionBlocked ?? undefined}
          className={`px-3 py-1.5 rounded text-[11px] font-bold border transition-colors flex items-center gap-1.5 ${
            promoteDisabled
              ? 'bg-surface-veil text-text-subtle border-border-subtle cursor-not-allowed'
              : 'bg-positive-bg text-positive border-positive hover:bg-surface-raised'
          }`}
        >
          <Trophy className="w-3.5 h-3.5" />
          <span>{isBusy('promote_challenger') ? 'PROMOTING…' : 'PROMOTE CHALLENGER'}</span>
        </button>

        <button
          onClick={onReject}
          disabled={!kernelWired || busy !== null || trial.state === 'PROMOTED'}
          title={
            !kernelWired
              ? 'promotion controllers are not wired on this deployment'
              : trial.state === 'PROMOTED'
                ? 'already PROMOTED — no reversal is offered'
                : undefined
          }
          className={`px-3 py-1.5 rounded text-[11px] font-bold border transition-colors flex items-center gap-1.5 ${
            !kernelWired || trial.state === 'PROMOTED' || busy !== null
              ? 'bg-surface-veil text-text-subtle border-border-subtle cursor-not-allowed'
              : 'bg-warning-bg text-warning border-warning hover:bg-surface-raised'
          }`}
        >
          <XCircle className="w-3.5 h-3.5" />
          <span>{isBusy('promote_challenger') ? 'REJECTING…' : 'REJECT CHALLENGER'}</span>
        </button>

        {promotionBlocked && (
          <span className="text-[10px] text-text-subtle leading-relaxed">
            promotion unavailable: {promotionBlocked}
          </span>
        )}
      </div>
    </article>
  );
}

// --------------------------------------------------------------- side rendering

function SideTable({
  label,
  side,
}: {
  label: string;
  side: AdaptedArenaTrial['champion'];
}) {
  return (
    <div className="bg-surface-sunken border border-border-subtle rounded p-3">
      <div className="text-[9px] uppercase text-text-subtle mb-1.5">{label}</div>
      {side === null ? (
        <div className="text-[11px] text-warning">Not run — this side has no result yet.</div>
      ) : (
        <div className="grid grid-cols-2 gap-y-1 text-[11px]">
          <Metric label="side" value={side.side} />
          <Metric label="trades" value={fmtNum(side.trades)} />
          <Metric label="pnl" value={fmtUsd(side.pnl)} />
          <Metric label="dir. accuracy" value={fmtPct(side.directionalAccuracyPct)} />
          <Metric label="max drawdown" value={fmtPct(side.maxDrawdownPct)} />
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-[9px] text-text-subtle uppercase block">{label}</span>
      <span className="text-text-strong font-mono">{value}</span>
    </div>
  );
}

// ------------------------------------------------------------------- badges

/** Wiring and kernel-wiredness are separate facts and get separate badges. */
function WiringBadge({ wired }: { wired: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
        wired ? 'bg-positive-bg text-positive border-positive' : 'bg-warning-bg text-warning border-warning'
      }`}
    >
      {wired ? <CheckCircle2 className="w-3 h-3" /> : <Ban className="w-3 h-3" />}
      registry {wired ? 'wired' : 'not wired'}
    </span>
  );
}

function KernelBadge({ wired }: { wired: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
        wired ? 'bg-positive-bg text-positive border-positive' : 'bg-warning-bg text-warning border-warning'
      }`}
    >
      {wired ? <CheckCircle2 className="w-3 h-3" /> : <Ban className="w-3 h-3" />}
      promotion {wired ? 'available' : 'would refuse'}
    </span>
  );
}

function StateBadge({ state }: { state: AdaptedArenaTrial['state'] }) {
  const cls = {
    PROPOSED: 'bg-surface-veil text-text-muted border-border-subtle',
    EVALUATED: 'bg-info-bg text-accent border-accent',
    PROMOTED: 'bg-positive-bg text-positive border-positive',
    REJECTED: 'bg-warning-bg text-warning border-warning',
  }[state];
  return (
    <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold border ${cls}`}>
      {state}
    </span>
  );
}

/**
 * PROMOTE and REJECT are the server's comparison verdicts. INSUFFICIENT_EVIDENCE gets its
 * own treatment because it is a different kind of statement: not a verdict at all.
 */
function RecommendationBadge({
  recommendation,
}: {
  recommendation: AdaptedArenaTrial['recommendation'];
}) {
  if (recommendation.insufficientEvidence) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold border bg-warning-bg text-warning border-warning">
        <Ban className="w-3 h-3" />
        INSUFFICIENT_EVIDENCE
      </span>
    );
  }
  const promote = recommendation.recommendation === 'PROMOTE';
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
        promote ? 'bg-positive-bg text-positive border-positive' : 'bg-warning-bg text-warning border-warning'
      }`}
    >
      {promote ? <Trophy className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
      {recommendation.recommendation}
    </span>
  );
}

export default ArenaWorkspace;