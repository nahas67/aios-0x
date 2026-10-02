/**
 * The empty / absent distinction, which is a correctness property rather than a style one.
 *
 * CONSTITUTION §3.2: missing data means UNKNOWN, never a default value. The test that
 * matters most here is `an unavailable source is never reported as empty`, because that
 * exact substitution shipped: a dead kernel produced an empty positions table whose caption
 * read "reported by /api/v1/positions", telling an operator the instrument list was empty
 * when in fact nothing had been asked.
 */
import { describe, expect, it } from 'vitest';
import { classifyList, describe as describeState, isAbsence, rowsIfAvailable } from './stateView';

const FROM = '/api/v1/positions';

describe('classifyList', () => {
  it('reports a non-empty source as ready, with a count', () => {
    expect(classifyList([1, 2, 3], FROM)).toEqual({ kind: 'ready', count: 3 });
  });

  it('reports a genuinely empty array as empty, and names who looked', () => {
    expect(classifyList([], FROM)).toEqual({ kind: 'empty', observedFrom: FROM });
  });

  // THE TEST THAT MATTERS. An unwired kernel, a 500, a component that is simply not wired
  // in this deployment — all of them look like "no data" to a `.length === 0` check, and
  // all of them are a lie when rendered as "there are none".
  it('never reports an unavailable source as empty', () => {
    for (const source of [
      { available: false, reason: 'kernel unwired' },
      { ok: false, reason: '503' },
      null,
      undefined,
      { available: false },
    ]) {
      const state = classifyList(source as never, FROM);
      expect(state.kind, `${JSON.stringify(source)} was classified as ${state.kind}`).not.toBe('empty');
      expect(state.kind).toBe('unavailable');
    }
  });

  it('carries the reason through, so the operator learns why', () => {
    const state = classifyList({ available: false, reason: 'IBOR adapter unwired' }, FROM);
    expect(state).toEqual({ kind: 'unavailable', reason: 'IBOR adapter unwired', observedFrom: FROM });
  });

  it('supplies a reason when the source declines to give one', () => {
    const state = classifyList({ available: false }, FROM);
    expect(state.kind === 'unavailable' && state.reason).toBeTruthy();
  });

  it('reports loading as loading', () => {
    expect(classifyList({ loading: true }, FROM)).toEqual({ kind: 'loading' });
  });

  // A payload that is neither a list nor a recognisable unavailability is not something to
  // summarise. Guessing here would be inventing structure.
  it('refuses to interpret an unexpected payload shape', () => {
    const state = classifyList({ weird: true } as never, FROM);
    expect(state.kind).toBe('unavailable');
    expect(state.kind === 'unavailable' && state.reason).toContain('unexpected payload');
  });
});

describe('describe', () => {
  it('says a source reported zero only when it did', () => {
    expect(describeState({ kind: 'empty', observedFrom: FROM }, 'open positions')).toBe(
      `No open positions. ${FROM} reported zero.`,
    );
  });

  // The sentence the old code got wrong. "reported" is a claim about the source, so it may
  // only appear when the source actually answered.
  it('never says "reported" about a source that could not be read', () => {
    const sentence = describeState(
      { kind: 'unavailable', reason: 'kernel unwired', observedFrom: FROM },
      'working orders',
    );
    expect(sentence).not.toContain('reported');
    expect(sentence).toContain('could be read');
    expect(sentence).toContain('kernel unwired');
    // And it must say outright that this is not evidence of absence.
    expect(sentence).toContain('not a statement about whether any exist');
  });

  it('states the count when there is one', () => {
    expect(describeState({ kind: 'ready', count: 4 }, 'fills')).toBe('4 fills');
  });

  it('describes loading without claiming anything about the result', () => {
    expect(describeState({ kind: 'loading' }, 'orders')).toBe('Loading orders…');
  });
});

describe('isAbsence', () => {
  it('is true only for unavailable, so a caller can style absence differently', () => {
    expect(isAbsence({ kind: 'unavailable', reason: 'x', observedFrom: FROM })).toBe(true);
    expect(isAbsence({ kind: 'empty', observedFrom: FROM })).toBe(false);
    expect(isAbsence({ kind: 'ready', count: 1 })).toBe(false);
    expect(isAbsence({ kind: 'loading' })).toBe(false);
  });
});

describe('rowsIfAvailable', () => {
  it('returns the rows for a real array', () => {
    expect(rowsIfAvailable(['a', 'b'])).toEqual(['a', 'b']);
  });

  // null, not []: a caller that ignores the distinction gets `rows.length` on null and a
  // visible crash in development, rather than a table that silently reads as empty in
  // production.
  it('returns null rather than an empty array when the source is not a list', () => {
    expect(rowsIfAvailable(null)).toBeNull();
    expect(rowsIfAvailable(undefined)).toBeNull();
    expect(rowsIfAvailable({ available: false, reason: 'unwired' })).toBeNull();
  });

  it('keeps a genuinely empty array as an empty array', () => {
    // The distinction that matters: [] is a real observation and must not be turned into
    // null, or a legitimately empty book would render as unavailable.
    expect(rowsIfAvailable([])).toEqual([]);
  });
});
