/**
 * The chat view model, and the property it exists to hold.
 *
 * The load-bearing test is `carries nothing executable`. An agent's suggested actions are
 * shown in the UI, and the temptation is to make them clickable. There is no server-side
 * dispatch for those strings — `core/agent_advisory.py` imports neither the control plane
 * nor any order sink — so a button would advertise a capability the platform does not
 * have. This deep-walks the view model and asserts no value is callable, which makes
 * "inert" a checked property instead of a comment someone can wave past.
 */
import { describe, expect, it } from 'vitest';
import { isAdvisory, toChatView } from './chatView';

function advisory(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    kind: 'advisory',
    authority: 'ADVISORY',
    agent: 'c4_strategy.agent',
    answer: 'c4_strategy.agent has recorded: 3 opportunities.',
    advisory: {
      authority: 'ADVISORY',
      agent_id: 'c4_strategy.agent',
      community: 'c4_strategy',
      role: 'STRATEGIST',
      stance: 'RECORDED',
      attribution: { mode: 'deterministic', note: 'composed from the audit record' },
      evidence: [
        { label: 'ranked opportunities', source: 'opportunities', available: true, rows: 3, detail: '3 record(s)' },
        { label: 'portfolio', source: 'portfolio', available: false, detail: 'unavailable (unwired)' },
      ],
      proposed_actions: ['set_autonomy supervised', 'pause_trading'],
      limitations: ['Advisory only. This agent cannot place, cancel or authorise anything.'],
      ...overrides,
    },
  };
}

/** Every callable anywhere in a structure. */
function callablesIn(value: unknown, path = '$', found: string[] = []): string[] {
  if (typeof value === 'function') {
    found.push(path);
    return found;
  }
  if (value === null || typeof value !== 'object') return found;
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    callablesIn(child, `${path}.${key}`, found);
  }
  return found;
}

describe('the advisory view model', () => {
  it('carries nothing executable', () => {
    // Every branch, not just the advisory one: a function smuggled into any payload would
    // be a place the renderer could be handed something to invoke.
    for (const response of [
      advisory(),
      { kind: 'command', action: 'pause_trading', result: { paused: true }, answer: 'ok' },
      { kind: 'denied', action: 'approve_live_capital', answer: 'DENIED' },
      { kind: 'query', query: 'P&L analysis', answer: 'ok' },
      { kind: 'help', answer: 'help text' },
    ]) {
      expect(callablesIn(toChatView(response))).toEqual([]);
    }
  });

  it('labels every suggestion as not executed, inside the view model', () => {
    const view = toChatView(advisory());
    expect(isAdvisory(view)).toBe(true);
    if (!isAdvisory(view)) return;
    expect(view.suggestions).toHaveLength(2);
    for (const suggestion of view.suggestions) {
      expect(suggestion).toContain('not executed');
    }
    expect(view.suggestions.join(' ')).toContain('set_autonomy supervised');
    expect(view.suggestions.join(' ')).toContain('pause_trading');
  });

  it('drops a non-string suggestion rather than rendering an object', () => {
    const view = toChatView(
      advisory({ proposed_actions: ['pause_trading', { action: 'create_order' }, 42, null] }),
    );
    if (!isAdvisory(view)) throw new Error('expected an advisory view');
    expect(view.suggestions).toEqual(['It would suggest (not executed): pause_trading']);
  });

  it('surfaces the agent, its community and its role together', () => {
    const view = toChatView(advisory());
    expect(view.title).toBe('c4_strategy.agent · c4_strategy · STRATEGIST');
  });

  it('shows the stance as a badge and never hides it', () => {
    for (const stance of ['RECORDED', 'MODEL', 'UNKNOWN']) {
      const view = toChatView(advisory({ stance }));
      if (!isAdvisory(view)) throw new Error('expected an advisory view');
      expect(view.stance).toBe(stance);
    }
  });

  it('marks an unreadable-evidence answer destructive rather than neutral', () => {
    // UNKNOWN is the "we could not tell you" case, and it must not read as a clean answer.
    const view = toChatView(advisory({ stance: 'UNKNOWN' }));
    expect(view.tone).toBe('destructive');
  });

  it('names the source of every piece of evidence', () => {
    const view = toChatView(advisory());
    if (!isAdvisory(view)) throw new Error('expected an advisory view');
    // The source is what lets an operator audit the answer rather than take it on trust.
    expect(view.evidence.map((e) => e.source)).toEqual(['opportunities', 'portfolio']);
    expect(view.evidence[1].available).toBe(false);
  });

  it('always names how the text was produced', () => {
    const deterministic = toChatView(advisory());
    if (!isAdvisory(deterministic)) throw new Error('expected an advisory view');
    expect(deterministic.attribution).toContain('deterministic');

    const modelled = toChatView(
      advisory({ attribution: { mode: 'model', model: 'test-model', note: 'synthesised' } }),
    );
    if (!isAdvisory(modelled)) throw new Error('expected an advisory view');
    expect(modelled.attribution).toContain('model (test-model)');
  });

  it('falls back to UNKNOWN when the advisory payload is missing entirely', () => {
    const view = toChatView({ kind: 'advisory', answer: 'something' });
    if (!isAdvisory(view)) throw new Error('expected an advisory view');
    expect(view.stance).toBe('UNKNOWN');
    expect(view.tone).toBe('destructive');
    expect(view.suggestions).toEqual([]);
  });

  it('handles an advisory with no agent resolved', () => {
    const view = toChatView({ kind: 'advisory', agent: null, answer: 'UNKNOWN: no agent matches' });
    if (!isAdvisory(view)) throw new Error('expected an advisory view');
    expect(view.agent).toBeNull();
    expect(view.body).toContain('no agent matches');
  });
});

describe('the other chat kinds', () => {
  it('renders an executed command as a receipt, with its audit payload', () => {
    const view = toChatView({ kind: 'command', action: 'pause_trading', result: { paused: true }, answer: 'ok' });
    if (view.kind !== 'command') throw new Error('expected a command view');
    expect(view.kind).toBe('command');
    expect(view.title).toBe('Control action executed: pause_trading');
    expect(view.body).toContain('audit log');
    expect(view.payload).toEqual({ paused: true });
  });

  it('never dresses a denial as neutral', () => {
    const view = toChatView({ kind: 'denied', action: 'approve_live_capital', answer: 'DENIED: VIEWER may not perform' });
    expect(view.kind).toBe('denied');
    expect(view.tone).toBe('destructive');
    expect(view.body).toContain('may not perform');
  });

  it('renders an error in the destructive tone', () => {
    expect(toChatView({ kind: 'error', answer: 'boom' }).tone).toBe('destructive');
  });

  it('shows help as help and a query under its label', () => {
    expect(toChatView({ kind: 'help', answer: 'ASK…' }).title).toBe('What I understand');
    expect(toChatView({ kind: 'query', query: 'P&L analysis', answer: 'x' }).title).toBe('P&L analysis');
  });

  it('shows an unrecognised kind rather than rendering an empty bubble', () => {
    const view = toChatView({ kind: 'something_new', answer: 'body text' });
    expect(view.kind).toBe('unknown');
    expect(view.tone).toBe('warning');
    expect(view.title).toContain('something_new');
    expect(view.body).toBe('body text');
  });

  it('survives a non-object response', () => {
    for (const bad of [null, undefined, 42, 'text']) {
      const view = toChatView(bad);
      expect(view.kind).toBe('unknown');
    }
  });
});
