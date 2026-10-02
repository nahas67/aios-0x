/**
 * Operator layout normalisation — the property that keeps a saved layout from damaging the
 * console.
 *
 * THE HEADLINE TEST. `normalizeLayout` is total. A stored layout is a snapshot of the tab
 * list as it was when saved, and tabs are ADDED over time (`certification`, then `chat`). A
 * naive restore would drop or mis-order workspaces that did not exist when the layout was
 * written, and since layouts are restored on every page load, that is a persistent silent
 * degradation rather than a glitch — an operator would come back to a console missing a
 * screen with no way to tell which or why.
 */
import { describe, expect, it } from 'vitest';
import { WORKSPACE_TABS, type WorkspaceTab } from '../types';
import {
  canHide,
  defaultLayout,
  hiddenCount,
  isDefault,
  isHidden,
  moveTab,
  normalizeLayout,
  readStoredLayout,
  setHidden,
  visibleTabs,
  type WorkspaceLayout,
} from './layout';

const TABS = WORKSPACE_TABS;

describe('defaultLayout', () => {
  it('shows everything, in architecture order', () => {
    const layout = defaultLayout(TABS);
    expect(layout.hidden).toEqual([]);
    expect(layout.order).toEqual([...TABS]);
  });

  it('copies the tab list rather than aliasing it', () => {
    // 'risk' is already in TABS, so pushing it proved nothing. Push an id that is not,
    // which is the only way to tell a copy from an alias.
    const source = [...TABS] as WorkspaceTab[];
    const layout = defaultLayout(source);
    source.push('ghost_tab' as WorkspaceTab);
    expect(layout.order).not.toContain('ghost_tab');
    expect(layout.order).toHaveLength(TABS.length);
  });
});

describe('normalizeLayout is total', () => {
  it('passes a valid layout through unchanged', () => {
    const layout: WorkspaceLayout = {
      order: ['risk', ...TABS.filter((t) => t !== 'risk')],
      hidden: ['risk'],
    };
    const out = normalizeLayout(layout, TABS);
    expect(out.order).toHaveLength(TABS.length);
    expect(out.hidden).toEqual(['risk']);
  });

  // THE HEADLINE PROPERTY. A tab added since the layout was saved must appear, or the
  // console silently loses a screen every reload for that operator.
  it('appends a tab added since the layout was saved', () => {
    const old = TABS.filter((t) => t !== 'chat');
    const stored = { order: old, hidden: [] };
    const out = normalizeLayout(stored, TABS);
    expect(out.order).toHaveLength(TABS.length);
    expect(out.order).toContain('chat');
    // Appended at the end rather than interleaved: guessing where a new tab "belongs"
    // would scramble an order the operator deliberately set.
    expect(out.order[out.order.length - 1]).toBe('chat');
  });

  it('drops an id that no longer exists', () => {
    const stored = { order: [...TABS, 'ghost_tab' as WorkspaceTab], hidden: ['phantom' as WorkspaceTab] };
    const out = normalizeLayout(stored, TABS);
    expect(out.order).not.toContain('ghost_tab');
    expect(out.hidden).not.toContain('phantom');
    expect(out.order).toHaveLength(TABS.length);
  });

  it('keeps the first of a duplicated id, so no tab appears twice', () => {
    const stored = { order: ['risk', 'risk', 'audit'] as WorkspaceTab[], hidden: [] };
    const out = normalizeLayout(stored, TABS);
    expect(out.order.filter((t) => t === 'risk')).toHaveLength(1);
    // The first occurrence wins, so the operator's chosen position survives.
    expect(out.order.indexOf('risk')).toBe(0);
    expect(new Set(out.order).size).toBe(TABS.length);
  });

  it('de-duplicates a repeated hidden id', () => {
    const stored = { order: [...TABS], hidden: ['risk', 'risk'] as WorkspaceTab[] };
    expect(normalizeLayout(stored, TABS).hidden).toEqual(['risk']);
  });

  it('survives junk', () => {
    for (const junk of [null, undefined, 42, 'text', [], { order: 'nope' }, { order: [1, 2] }]) {
      const out = normalizeLayout(junk, TABS);
      // Whatever the input, the result renders: every live tab, exactly once.
      expect(out.order).toHaveLength(TABS.length);
      expect(new Set(out.order).size).toBe(TABS.length);
      expect(out.hidden).toEqual([]);
    }
  });

  it('is idempotent', () => {
    const stored = { order: ['risk', 'ghost' as WorkspaceTab, 'risk'] as WorkspaceTab[], hidden: ['risk'] };
    const once = normalizeLayout(stored, TABS);
    expect(normalizeLayout(once, TABS)).toEqual(once);
  });

  it('preserves the relative order of everything it kept', () => {
    const stored = { order: ['audit', 'risk', 'markets', 'ghost' as WorkspaceTab] as WorkspaceTab[], hidden: [] };
    const out = normalizeLayout(stored, TABS).order;
    expect(out.indexOf('audit')).toBeLessThan(out.indexOf('risk'));
    expect(out.indexOf('risk')).toBeLessThan(out.indexOf('markets'));
  });
});

describe('visibleTabs', () => {
  it('excludes hidden tabs and keeps the rest in order', () => {
    const layout = normalizeLayout(
      { order: ['audit', 'risk', 'markets'], hidden: ['risk'] },
      TABS,
    );
    const visible = visibleTabs(layout, TABS);
    expect(visible).not.toContain('risk');
    expect(visible.indexOf('audit')).toBeLessThan(visible.indexOf('markets'));
    expect(visible).toHaveLength(TABS.length - 1);
  });

  it('shows everything by default', () => {
    expect(visibleTabs(defaultLayout(TABS), TABS)).toHaveLength(TABS.length);
  });

  // The property that keeps a saved layout from ever REMOVING a workspace from the console.
  it('always yields every tab that is not hidden, even from a stale layout', () => {
    const stale = { order: ['risk'] as WorkspaceTab[], hidden: ['risk'] as WorkspaceTab[] };
    const visible = visibleTabs(stale, TABS);
    expect(visible).toHaveLength(TABS.length - 1);
    expect(visible).toContain('chat');
  });
});

describe('moveTab', () => {
  it('moves one position up or down', () => {
    const layout = defaultLayout(TABS);
    const index = layout.order.indexOf('risk');
    const down = moveTab(layout, 'risk', 1);
    expect(down.order[index + 1]).toBe('risk');
    const up = moveTab(down, 'risk', -1);
    expect(up.order[index]).toBe('risk');
  });

  it('clamps at the ends rather than wrapping or dropping', () => {
    const layout = defaultLayout(TABS);
    const first = layout.order[0];
    expect(moveTab(layout, first, -1).order[0]).toBe(first);
    const last = layout.order[layout.order.length - 1];
    expect(moveTab(layout, last, 1).order[layout.order.length - 1]).toBe(last);
  });

  it('is a no-op for a tab it does not know, rather than inventing one', () => {
    const layout = defaultLayout(TABS);
    const out = moveTab(layout, 'ghost' as WorkspaceTab, 1);
    expect(out).toBe(layout);
  });

  it('never changes the visible set', () => {
    const layout = setHidden(defaultLayout(TABS), 'settings', true);
    const before = visibleTabs(layout, TABS);
    const after = visibleTabs(moveTab(layout, 'risk', 3), TABS);
    expect([...after].sort()).toEqual([...before].sort());
  });

  it('keeps every tab exactly once after a move', () => {
    const out = moveTab(defaultLayout(TABS), 'overview', 5);
    expect(new Set(out.order).size).toBe(TABS.length);
  });
});

describe('setHidden', () => {
  it('hides and shows symmetrically', () => {
    // 'risk' rather than 'settings': settings is the non-hideable recovery path.
    const hidden = setHidden(defaultLayout(TABS), 'risk', true);
    expect(isHidden(hidden, 'risk')).toBe(true);
    const shown = setHidden(hidden, 'risk', false);
    expect(isHidden(shown, 'risk')).toBe(false);
  });

  it('is idempotent', () => {
    const once = setHidden(defaultLayout(TABS), 'risk', true);
    expect(setHidden(once, 'risk', true)).toEqual(once);
    expect(hiddenCount(setHidden(once, 'risk', true))).toBe(1);
  });

  it('keeps hidden sorted by display order, so equal layouts compare equal', () => {
    // Without this, the stored value churns between reads purely on ordering, and a stable
    // layout would keep rewriting localStorage.
    const layout = normalizeLayout({ order: ['risk', 'audit'], hidden: ['audit', 'risk'] }, TABS);
    expect(layout.hidden).toEqual(['risk', 'audit']);
  });

  it('counts correctly, and does not normalise against an empty tab list', () => {
    // Regression: an earlier `hiddenCount` normalised first, and normalisation filters
    // against the live tab list — so an empty list returned 0 for every layout.
    const layout = setHidden(defaultLayout(TABS), 'risk', true);
    expect(hiddenCount(layout)).toBe(1);
    expect(hiddenCount(setHidden(layout, 'audit', true))).toBe(2);
  });
});

describe('the recovery path cannot be hidden', () => {
  // The one-way-door trap. Settings holds the layout editor; hide it and the operator has
  // removed the only control that would restore their navigation, with no other route back.
  // A cosmetic toggle that can do that has a terrible harm-to-intent ratio.
  it('refuses to hide Settings', () => {
    const layout = setHidden(defaultLayout(TABS), 'settings', true);
    expect(isHidden(layout, 'settings')).toBe(false);
    expect(layout.hidden).toEqual([]);
    expect(layout).toEqual(defaultLayout(TABS));
  });

  it('corrects a stored layout that hid Settings', () => {
    // Enforced on READ, not only on write: an operator on an older build could have saved
    // exactly this, and the only alternative would be to strand them until a new build.
    const stored = { order: [...TABS], hidden: ['settings'] as WorkspaceTab[] };
    const out = normalizeLayout(stored, TABS);
    expect(out.hidden).toEqual([]);
    expect(visibleTabs(out, TABS)).toContain('settings');
  });

  it('keeps the layout editor reachable however the layout was assembled', () => {
    for (const stored of [
      { order: ['settings'], hidden: ['settings'] },
      { order: [], hidden: ['settings'] },
      null,
      'garbage',
    ]) {
      expect(visibleTabs(normalizeLayout(stored, TABS), TABS), JSON.stringify(stored)).toContain('settings');
    }
  });

  it('still allows every other workspace to be hidden', () => {
    const layout = defaultLayout(TABS);
    for (const tab of TABS.filter((t) => t !== 'settings')) {
      expect(setHidden(layout, tab, true).hidden, `could not hide ${tab}`).toContain(tab);
    }
  });

  it('reports Settings as hideable = false and everything else true', () => {
    expect(canHide('settings')).toBe(false);
    for (const tab of TABS.filter((t) => t !== 'settings')) expect(canHide(tab)).toBe(true);
  });
});

describe('isDefault', () => {
  it('is true only for the untouched layout', () => {
    expect(isDefault(defaultLayout(TABS), TABS)).toBe(true);
    expect(isDefault(setHidden(defaultLayout(TABS), 'risk', true), TABS)).toBe(false);
    expect(isDefault(moveTab(defaultLayout(TABS), 'risk', 1), TABS)).toBe(false);
  });

  it('is true for a reordered layout that normalises back to the original', () => {
    const shuffled = { order: [...TABS].reverse(), hidden: [] };
    expect(isDefault(normalizeLayout(shuffled, TABS), TABS)).toBe(false);
  });
});

describe('readStoredLayout', () => {
  function withStorage(store: Record<string, string> | 'throws', fn: () => WorkspaceLayout): WorkspaceLayout {
    const g = globalThis as Record<string, unknown>;
    g.window = {
      localStorage: {
        getItem: (k: string) => {
          if (store === 'throws') throw new Error('storage disabled');
          return store[k] ?? null;
        },
        setItem: () => undefined,
      },
    };
    try {
      return fn();
    } finally {
      delete g.window;
    }
  }

  it('restores a stored layout', () => {
    const out = withStorage({ 'aios.layout': JSON.stringify({ order: ['risk'], hidden: ['audit'] }) }, () =>
      readStoredLayout(TABS),
    );
    expect(out.hidden).toEqual(['audit']);
    expect(out.order).toHaveLength(TABS.length);
  });

  // A layout is restored on EVERY page load, so any parse failure is persistent rather
  // than transient. It must degrade to the default, not to a broken console.
  it('falls back to the default on malformed JSON', () => {
    const out = withStorage({ 'aios.layout': '{not json' }, () => readStoredLayout(TABS));
    expect(out.order).toEqual([...TABS]);
    expect(out.hidden).toEqual([]);
  });

  it('falls back to the default when storage throws', () => {
    const out = withStorage('throws', () => readStoredLayout(TABS));
    expect(out.order).toHaveLength(TABS.length);
  });

  it('falls back to the default when nothing is stored', () => {
    expect(withStorage({}, () => readStoredLayout(TABS)).order).toEqual([...TABS]);
  });
});
