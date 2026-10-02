/**
 * One vocabulary for "there is nothing here", so it cannot quietly mean two things.
 *
 * THE DEFECT THIS EXISTS TO FIX
 * =============================
 * §3.2: missing data means NO TRADE / UNKNOWN, never a default value. The console had a
 * proper `<Unavailable>` component and used it in most views — but `LiveTradingWorkspace`
 * collapsed it first:
 *
 *     const workingOrders = useMemo(() => {
 *       if (!orders || "unavailable" in orders) return [];      // <-- unavailable becomes empty
 *       ...
 *     })
 *
 * and then rendered, for that same panel:
 *
 *     "No working orders reported by /api/v1/orders."
 *
 * which asserts the endpoint reported nothing. It did not report anything — it could not be
 * asked. "We looked and there are none" and "we could not look" are different facts, and
 * collapsing them lets a console tell an operator its instrument list is empty when the
 * kernel is actually down. That is the exact substitution §3.2 forbids, and it was
 * invisible because both paths render the same grey text.
 *
 * WHY A TYPE RATHER THAN A HELPER FUNCTION
 * =========================================
 * A function `emptyIf(rows.length === 0)` would be callable with `[]` and return "empty",
 * with no provenance — which is how the bug was written in the first place. Here, `empty`
 * REQUIRES an `observedFrom` naming the source that genuinely reported zero, and `unavailable`
 * REQUIRES a reason. You cannot construct "empty" without saying who looked. The distinction
 * is in the signature, so forgetting it is a type error rather than a subtle lie.
 *
 * Pure and DOM-free, for the same reason `chatView.ts` is: this repo has no DOM test
 * environment, and the logic worth testing must not require a browser to reach.
 */

/** A fetch that succeeded and genuinely returned nothing. */
export interface ObservedEmpty {
  ok: true;
  rows: readonly unknown[];
  /** The endpoint, view or adapter that reported zero. Shown to the operator. */
  observedFrom: string;
}

/** A fetch that could not be completed. The rows may well exist; we did not get to see them. */
export interface SourceUnavailable {
  ok: false;
  reason: string;
  observedFrom?: string;
}

export type ListSource =
  | ObservedEmpty
  | SourceUnavailable
  | {
      /** Still in flight. */
      loading: true;
    }
  // The repo's own absence marker (`adapters/absent.ts`): `{ unavailable: string }`.
  // Recognised explicitly because it is the shape most views actually carry. A classifier
  // that did not know it would treat the marker as "a payload", which is one more way an
  // unwired component comes to look like a populated one.
  | { unavailable: string };

export type SurfaceState =
  | { kind: 'ready'; count: number }
  | { kind: 'loading' }
  | { kind: 'empty'; observedFrom: string }
  | { kind: 'unavailable'; reason: string; observedFrom: string };

/**
 * Classify a list-shaped source. The only route to `'empty'`.
 *
 * `available: false` is accepted because the adapters in this repo use that shape for
 * honest absence (`{ available: false, reason }`), and treating it as "empty" is precisely
 * the bug being fixed.
 */
export function classifyList(
  source: readonly unknown[] | ListSource | { available: boolean; reason?: string } | null | undefined,
  observedFrom: string,
): SurfaceState {
  if (source === null || source === undefined) {
    // No payload at all is absence, not emptiness.
    return { kind: 'unavailable', reason: 'no payload', observedFrom };
  }
  if (!Array.isArray(source)) {
    if ('loading' in source && source.loading) return { kind: 'loading' };
    if ('unavailable' in source && typeof source.unavailable === 'string') {
      return { kind: 'unavailable', reason: source.unavailable, observedFrom };
    }
    const record = source as { available?: boolean; reason?: string; ok?: boolean };
    if (record.available === false || record.ok === false) {
      return {
        kind: 'unavailable',
        reason: record.reason ?? 'source reported unavailable',
        observedFrom,
      };
    }
    // A non-array, non-unavailable object is not something this can summarise honestly.
    return { kind: 'unavailable', reason: 'unexpected payload shape', observedFrom };
  }
  if (source.length === 0) {
    return { kind: 'empty', observedFrom };
  }
  return { kind: 'ready', count: source.length };
}

/**
 * Narrow a query result into a plain array, refusing to invent one.
 *
 * Returns `null` when the source is unavailable, so a caller that ignores the distinction
 * gets a type error rather than an empty table that reads as "there are none".
 */
export function rowsIfAvailable<T>(
  source: readonly T[] | { available: boolean; reason?: string } | null | undefined,
): readonly T[] | null {
  if (source === null || source === undefined) return null;
  if (Array.isArray(source)) return source;
  return null;
}

/** The sentence to show. Never claims a source "reported" nothing it did not report. */
export function describe(state: SurfaceState, noun: string): string {
  switch (state.kind) {
    case 'ready':
      return `${state.count} ${noun}`;
    case 'loading':
      return `Loading ${noun}…`;
    case 'empty':
      return `No ${noun}. ${state.observedFrom} reported zero.`;
    case 'unavailable':
      return `No ${noun} could be read. ${state.observedFrom}: ${state.reason}. This is not a statement about whether any exist.`;
  }
}

/** True when the state means "we could not look", which must never render as "there are none". */
export function isAbsence(state: SurfaceState): boolean {
  return state.kind === 'unavailable';
}
