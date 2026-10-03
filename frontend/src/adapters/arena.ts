/**
 * arenaAdapter: GET /api/v1/arena -> the operator's champion/challenger read model.
 *
 * WHY THIS ADAPTER EXISTS AT ALL
 * ==============================
 * The endpoint answers `wired: false` rather than `{available: false}`, and the two are
 * not interchangeable. `/api/v1/arena` with no ChallengeRegistry on the composition root
 * returns `{wired: false, kernel_wired: false, trials: [], note: "..."}` — a payload the
 * server read perfectly well. Mapping that to this repo's `Unavailable` marker, or to an
 * empty trial list, would tell the operator one of two untrue things:
 *
 *   - "no trials"      -> claims somebody looked and was told the arena is empty.
 *   - "unavailable"    -> claims nobody could look.
 *
 * Neither happened. So `wired` is carried through as a first-class field and the view
 * renders a WIRING panel for it, separately from the empty-tries state. The
 * `Unavailable` return is reserved for the one real absence case: a payload this cannot
 * read as an arena at all.
 *
 * INSUFFICIENT_EVIDENCE IS NOT A NUMBER
 * ======================================
 * `ChallengerTrial.recommend()` (core/challenger.py) returns
 * `{"recommendation": "INSUFFICIENT_EVIDENCE"}` and nothing else until BOTH sides have
 * been run. That is not a narrow loss, not a zero margin, and not a tie. The adapter
 * therefore produces `insufficientEvidence: true` and nulls every comparison figure, so
 * a component cannot accidentally render the absence of a run as a number that happens
 * to be zero. `core/challenger.py` negates `max_drawdown_pct` before comparing (lower
 * drawdown is better); the adapter does NOT re-derive the recommendation, it passes the
 * server's verdict through and keeps the raw per-side figures beside it.
 */
import type {
  ArenaRecommendation,
  ArenaSide,
  ArenaTrial,
  ArenaVerdict,
  ArenaView,
} from "../api/types";
import { type Unavailable } from "./absent";

/** The metric a trial decides on, as the server named it. Unknown values pass through. */
export type ArenaMetric = "pnl" | "directional_accuracy_pct" | "max_drawdown_pct";

export interface AdaptedArenaSide {
  side: string;
  trades: number | null;
  pnl: number | null;
  directionalAccuracyPct: number | null;
  maxDrawdownPct: number | null;
}

export interface AdaptedArenaRecommendation {
  recommendation: ArenaRecommendation["recommendation"];
  /**
   * True exactly when the server said INSUFFICIENT_EVIDENCE — i.e. the trial has not
   * been run on both sides. Every figure below is null in that case, and this flag is
   * what a view must branch on rather than testing a number.
   */
  insufficientEvidence: boolean;
  metric: string | null;
  champion: number | null;
  challenger: number | null;
  margin: number | null;
  note: string | null;
}

export interface AdaptedArenaTrial {
  name: string;
  description: string;
  metric: string;
  state: ArenaTrial["state"];
  promotedBy: string | null;
  evaluatedAt: string | null;
  champion: AdaptedArenaSide | null;
  challenger: AdaptedArenaSide | null;
  recommendation: AdaptedArenaRecommendation;
  verdict: ArenaVerdict | null;
  notes: string[];
  /**
   * Whether promotion is even reachable for this trial, from the server's own fields:
   * a verdict must exist and the trial must not already be terminal. Promotion is
   * fail-closed server-side on both counts (`ChallengeRegistry.promote`); the view may
   * disable the button on this, and must not invent a way around it.
   */
  promotionPreconditionsMet: boolean;
  /** Why promotion is not reachable, when it is not. Null means nothing is blocking. */
  promotionBlockedReason: string | null;
}

export interface AdaptedArena {
  /** False = no ChallengeRegistry on the composition root. A wiring fact, not an empty arena. */
  wired: boolean;
  /** False = no promotion/rollback controllers. Promotion would be refused. */
  kernelWired: boolean;
  trials: AdaptedArenaTrial[];
  note: string;
}

const FALLBACK_NOTE =
  "/api/v1/arena returned no note; the absence of a note is not a statement about the arena.";

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function adaptSide(side: ArenaSide | null | undefined): AdaptedArenaSide | null {
  if (!side) return null;
  return {
    side: text(side.side) ?? "unknown",
    trades: num(side.trades),
    pnl: num(side.pnl),
    directionalAccuracyPct: num(side.directional_accuracy_pct),
    maxDrawdownPct: num(side.max_drawdown_pct),
  };
}

/**
 * Pass the server's recommendation through, and refuse to manufacture its numbers.
 *
 * The figures are read only from the compared branch. When the server reports
 * INSUFFICIENT_EVIDENCE it sends none, and inventing them from the per-side results
 * would be computing the recommendation again on the client — which is exactly the
 * authority this view must not have.
 */
export function adaptRecommendation(raw: ArenaRecommendation): AdaptedArenaRecommendation {
  const insufficient = raw.recommendation === "INSUFFICIENT_EVIDENCE";
  return {
    recommendation: raw.recommendation,
    insufficientEvidence: insufficient,
    metric: insufficient ? null : text(raw.metric) ?? null,
    champion: insufficient ? null : num(raw.champion),
    challenger: insufficient ? null : num(raw.challenger),
    margin: insufficient ? null : num(raw.margin),
    note: text(raw.note),
  };
}

/** Promotion is fail-closed on two server-side gates. Name whichever one blocks. */
function promotionBlockers(trial: AdaptedArenaTrial): string | null {
  if (trial.state === "PROMOTED") {
    return "already PROMOTED — promotion is irreversible by design and this view offers no reversal";
  }
  if (trial.state === "REJECTED") {
    return "REJECTED — a rejected trial is terminal; the registry records the rejection as evidence";
  }
  if (!trial.verdict) {
    return "no EvaluationRecord on this trial — promotion is refused without one";
  }
  if (trial.verdict.verdict.toUpperCase() !== "PASS") {
    return `evaluation verdict is ${trial.verdict.verdict}, not PASS — promotion is refused`;
  }
  return null;
}

function adaptTrial(raw: ArenaTrial): AdaptedArenaTrial {
  const trial: AdaptedArenaTrial = {
    name: text(raw.name) ?? "unknown trial",
    description: text(raw.description) ?? "",
    metric: text(raw.metric) ?? "pnl",
    state: raw.state,
    promotedBy: text(raw.promoted_by),
    evaluatedAt: text(raw.evaluated_at),
    champion: adaptSide(raw.champion),
    challenger: adaptSide(raw.challenger),
    recommendation: adaptRecommendation(raw.recommendation),
    verdict: raw.verdict ?? null,
    notes: Array.isArray(raw.notes) ? raw.notes.filter((n): n is string => typeof n === "string") : [],
    promotionPreconditionsMet: false,
    promotionBlockedReason: null,
  };
  const blocker = promotionBlockers(trial);
  trial.promotionBlockedReason = blocker;
  trial.promotionPreconditionsMet = blocker === null;
  return trial;
}

/**
 * Map `/api/v1/arena`.
 *
 * Returns `Unavailable` only when the payload is not an arena read model at all — a
 * shape this adapter cannot summarise without guessing. A well-formed payload with
 * `wired: false` is a SUCCESSFUL read of an unwired arena, and is returned as such.
 */
export function adaptArena(payload: ArenaView): AdaptedArena | Unavailable {
  if (typeof payload !== "object" || payload === null || !Array.isArray(payload.trials)) {
    return { unavailable: `${"/api/v1/arena"} did not return a readable arena read model.` };
  }
  return {
    wired: payload.wired === true,
    kernelWired: payload.kernel_wired === true,
    trials: payload.trials.map(adaptTrial),
    note: text(payload.note) ?? FALLBACK_NOTE,
  };
}

/**
 * Why the promote/reject control will be refused, whatever trial is selected.
 *
 * `kernel_wired` is the composition-root fact the operator cannot see from the button:
 * promotion refuses without the promotion and rollback controllers, so this is stated
 * on the button rather than discovered by pressing it.
 */
export function kernelBlocker(kernelWired: boolean): string | null {
  return kernelWired
    ? null
    : "promotion controllers are not wired on this deployment — promote_challenger will be refused";
}