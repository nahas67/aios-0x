/**
 * The §2 grouping gate: every workspace placed, none placed twice, none invented.
 *
 * The plan's gate was "17 workspaces all placed, no orphans". That is only meaningful if
 * "all" is measured against something that can grow, so every assertion here is written
 * against `WORKSPACE_TABS` — the runtime array the `WorkspaceTab` type is derived from —
 * rather than against a list written out again here. A test that restated the seventeen
 * names would still pass if an eighteenth tab were added to the union; this one will not.
 *
 * Both directions are checked, because each catches a different mistake:
 *   - a tab with no unit      (an orphan — the gate's actual subject)
 *   - a unit id that is not a layer, a §3 plane, or an explicit non-architecture group
 *     (an invented structure — the failure mode of the IA this replaced)
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { WORKSPACE_TABS } from '../types';
import {
  NON_HIDEABLE,
  defaultLayout,
  isHidden,
  normalizeLayout,
  setHidden,
  visibleTabs,
} from './layout';
import {
  LAYERS,
  LAYERS_WITHOUT_WORKSPACE,
  NAV_GROUPS,
  buildNavSections,
  placementOf,
  unitIdOf,
  type ArchitectureUnit,
} from './architectureLayers';

const LAYER_IDS = LAYERS.map((l) => l.id);

/** §3's planes that a workspace may legitimately be placed against. */
const CONTROL_PLANE_IDS = ['§3A', '§3B', '§3C', '§3D', '§3E', '§3F'];

const KNOWN_UNIT_IDS = new Set([
  ...LAYER_IDS,
  ...CONTROL_PLANE_IDS,
  'x-system',
  'x-tooling',
]);

describe('the §2 layer list', () => {
  // §2 defines exactly 25 LAYER boxes. If the architecture gains or loses one, this
  // fails and forces the whole grouping to be restated rather than quietly out of date.
  it('has the 25 layers ARCHITECTURE.txt section 2 defines', () => {
    expect(LAYERS).toHaveLength(25);
  });

  it('numbers them 1 to 25 with no gaps or repeats', () => {
    expect(LAYERS.map((l) => l.id)).toEqual(
      Array.from({ length: 25 }, (_, i) => `L${i + 1}`),
    );
  });

  it('names every layer', () => {
    for (const layer of LAYERS) {
      expect(layer.label.trim().length).toBeGreaterThan(3);
    }
  });

  // The name the plan called "Layer 7" without stating. §2 calls it STRATEGY
  // CERTIFICATION FIREWALL, and it is the gate that decides whether anything may trade —
  // which is why P5 exists.
  it('names L7 the strategy certification firewall', () => {
    expect(LAYERS.find((l) => l.id === 'L7')?.label).toBe('Strategy Certification Firewall');
  });
});

describe('every workspace is placed', () => {
  // Deliberately does not say "17" in its name: WORKSPACE_TABS grew when the
  // certification view was added, and a test name that pins a count goes quietly
  // stale while its assertion stays correct.
  it('places every tab, so there are no orphans', () => {
    const orphans = WORKSPACE_TABS.filter((tab) => placementOf(tab) === undefined);
    expect(orphans).toEqual([]);
  });

  it('places no tab in more than one unit', () => {
    const twice = WORKSPACE_TABS.filter((tab) => NAV_GROUPS.filter((g) => g.tabs.includes(tab)).length > 1);
    expect(twice).toEqual([]);
  });

  it('references no tab that does not exist', () => {
    const known = new Set<string>(WORKSPACE_TABS);
    for (const group of NAV_GROUPS) {
      for (const tab of group.tabs) {
        expect(known.has(tab)).toBe(true);
      }
    }
  });

  it('loses no tab between the union and the groups', () => {
    // Counted from both ends rather than compared as sets, so a tab that is both
    // dropped and duplicated shows up as a count mismatch rather than cancelling out.
    const grouped = NAV_GROUPS.reduce((n, g) => n + g.tabs.length, 0);
    expect(grouped).toBe(WORKSPACE_TABS.length);
  });
});

describe('no structure is invented to make the grouping fit', () => {
  // The IA this replaced was eight invented stage names. This is the check that keeps a
  // future editor from reintroducing them one friendly label at a time.
  it('uses only layer ids, §3 plane ids, or an explicit x- group', () => {
    for (const group of NAV_GROUPS) {
      expect(KNOWN_UNIT_IDS.has(group.id)).toBe(true);
    }
  });

  it('records a placement kind for every group', () => {
    for (const group of NAV_GROUPS) {
      expect(['layer', 'control-plane', 'not-architecture-derived']).toContain(group.placement);
    }
  });

  it('agrees with itself: a `layer` group names a real layer, and nothing else does', () => {
    for (const group of NAV_GROUPS) {
      const isLayerId = LAYER_IDS.includes(group.id as (typeof LAYER_IDS)[number]);
      expect(group.placement === 'layer').toBe(isLayerId);
    }
  });
});

describe('the navigation spine', () => {
  it('orders groups so layer groups appear in ascending layer order', () => {
    const seen = NAV_GROUPS.map((g) => g.id).filter((id) => LAYER_IDS.includes(id as never));
    const numbers = seen.map((id) => Number(id.slice(1)));
    expect(numbers).toEqual([...numbers].sort((a, b) => a - b));
  });

  it('has no empty group, since an empty heading is worse than an absent one', () => {
    for (const group of NAV_GROUPS) {
      expect(group.tabs.length).toBeGreaterThan(0);
    }
  });

  it('labels every group', () => {
    for (const group of NAV_GROUPS) {
      expect(group.label.trim().length).toBeGreaterThan(2);
    }
  });
});

describe('the gaps the grouping exposes', () => {
  // 25 layers, 12 of them carrying a screen, so 13 have none. Pinned because the count
  // IS the finding: a console that shows 12 of the architecture's 25 layers is not
  // showing the architecture. Surfacing L25 (the arena) moved the number by one; it did
  // not close the gap. If someone builds the L23 view, this fails again.
  it('reports 13 of 25 layers as having no workspace', () => {
    const withScreens = LAYER_IDS.filter((id) => NAV_GROUPS.some((g) => g.id === id));
    expect(withScreens).toHaveLength(12);
    expect(LAYERS_WITHOUT_WORKSPACE).toHaveLength(25 - withScreens.length);
    expect(LAYERS_WITHOUT_WORKSPACE).toHaveLength(13);
  });

  it('never lists a layer as missing that actually has a workspace', () => {
    const withScreens = new Set(NAV_GROUPS.map((g) => g.id));
    for (const entry of LAYERS_WITHOUT_WORKSPACE) {
      expect(withScreens.has(entry.id)).toBe(false);
    }
  });

  it('accounts for every layer exactly once, present or missing', () => {
    const withScreens = new Set(NAV_GROUPS.map((g) => g.id));
    const missing = new Set(LAYERS_WITHOUT_WORKSPACE.map((m) => m.id));
    for (const id of LAYER_IDS) {
      expect(withScreens.has(id) !== missing.has(id)).toBe(true);
    }
  });

  it('explains every missing layer', () => {
    for (const entry of LAYERS_WITHOUT_WORKSPACE) {
      expect(entry.note.trim().length).toBeGreaterThan(20);
    }
  });

  // §12's chain ends Memory → Counterfactual evaluation → Champion/Challenger. The
  // `arena` view surfaced L25, so the terminus is now reachable — but the chain's START is
  // still not, which is why L23 stays in the missing list and why this assertion is now
  // two-sided rather than "both ends missing".
  it('reaches the terminus of §12 while its start remains unreachable', () => {
    const missing = LAYERS_WITHOUT_WORKSPACE.map((m) => m.id);
    expect(missing).toContain('L23');
    expect(missing).not.toContain('L25');
    expect(placementOf('arena')?.id).toBe('L25');
  });
});

describe('every placed workspace is actually reachable', () => {
  // WHY THIS EXISTS. The checks above are all about PLACEMENT: a tab is in the union, it
  // belongs to a group, that group is a real layer. None of them notice that a tab can be
  // perfectly placed and still render nothing — a nav entry that opens a blank screen.
  //
  // That is not hypothetical in this repo. `OperatorChat` existed with a working HTTP
  // endpoint and ZERO call sites in the frontend, and the accent picker shipped as a
  // control wired to no effect. Both were invisible to every existing gate because both
  // were *present*. Presence is not reachability, and only a reachability check tells them
  // apart.
  //
  // Read from source rather than imported, because the render is a conditional inside one
  // large component — there is no seam to assert against. The same trade the theme
  // bootstrap test makes for `index.html`.

  const appSource = readFileSync(resolve(__dirname, '..', 'App.tsx'), 'utf-8');
  const railSource = readFileSync(resolve(__dirname, '..', 'components', 'LeftIntelligenceRail.tsx'), 'utf-8');

  it('renders every tab, so no nav entry opens a blank screen', () => {
    const blank = WORKSPACE_TABS.filter((tab) => !appSource.includes(`activeTab === '${tab}'`));
    expect(blank, `placed but never rendered: ${blank.join(', ')}`).toEqual([]);
  });

  it('gives every tab a label in the rail', () => {
    // Without this the rail shows an unlabelled slot, or — if the rail derives its own list
    // — drops the tab from navigation entirely while it still renders.
    const unlabelled = WORKSPACE_TABS.filter((tab) => !railSource.includes(`id: '${tab}'`));
    expect(unlabelled, `rendered but absent from the rail: ${unlabelled.join(', ')}`).toEqual([]);
  });

  it('renders nothing for a tab that is not in the union', () => {
    // The converse. A stray `activeTab === 'ghost'` branch would be unreachable code that
    // still type-checks as `never`, so nothing else would notice it.
    const branches = [...appSource.matchAll(/activeTab === '([a-z_]+)'/g)].map((m) => m[1]);
    const ghosts = branches.filter((tab) => !(WORKSPACE_TABS as readonly string[]).includes(tab));
    expect(ghosts, `rendered but not in WORKSPACE_TABS: ${ghosts.join(', ')}`).toEqual([]);
  });

  it('routes every tab through the rail and the workspace, never only one', () => {
    // A tab in the rail but not in NAV_GROUPS renders and navigates while claiming no
    // architecture placement — the split-brain the grouping gate exists to prevent.
    const grouped = new Set(NAV_GROUPS.flatMap((g) => g.tabs));
    const dangling = WORKSPACE_TABS.filter((tab) => !grouped.has(tab));
    expect(dangling).toEqual([]);
  });
});

describe('the operator layout cannot strand anyone', () => {
  // Phase 6 added reorder/hide. Hiding a workspace is presentation only — it cannot weaken a
  // control — but it CAN remove a workspace from the console, and one removal is fatal:
  // hiding Settings removes the layout editor, which is the only way to restore the layout.
  //
  // A cosmetic toggle that can create a one-way door is the worst harm-to-intent ratio in the
  // feature, so the rule lives in `lib/layout.ts` and is asserted here against the real tab
  // list rather than left to the button's `disabled` attribute.
  it('keeps the layout editor itself reachable', () => {
    for (const stored of [
      { order: ['settings'], hidden: ['settings'] },
      { order: [], hidden: ['settings'] },
      { order: [...WORKSPACE_TABS], hidden: ['settings'] },
      null,
      'garbage',
    ]) {
      const layout = normalizeLayout(stored, WORKSPACE_TABS);
      expect(visibleTabs(layout, WORKSPACE_TABS), JSON.stringify(stored)).toContain('settings');
    }
  });

  it('refuses to hide it through the setter too, not only on read', () => {
    const layout = setHidden(defaultLayout(WORKSPACE_TABS), 'settings', true);
    expect(isHidden(layout, 'settings')).toBe(false);
    expect(layout.hidden).toEqual([]);
  });

  it('still lets every other workspace be hidden, so the feature is not a no-op', () => {
    const layout = defaultLayout(WORKSPACE_TABS);
    const hideable = WORKSPACE_TABS.filter((tab) => !NON_HIDEABLE.includes(tab));
    expect(hideable.length).toBeGreaterThan(WORKSPACE_TABS.length - 2);
    for (const tab of hideable) {
      expect(isHidden(setHidden(layout, tab, true), tab), `could not hide ${tab}`).toBe(true);
    }
  });

  it('never lets a layout change which workspaces EXIST', () => {
    // Reordering and hiding are about the operator's list, never about the platform's. The
    // union is fixed by the architecture, and a layout may not add to or remove from it.
    const layout = normalizeLayout(
      { order: ['ghost' as never], hidden: ['phantom' as never] },
      WORKSPACE_TABS,
    );
    expect(new Set(layout.order)).toEqual(new Set(WORKSPACE_TABS));
  });

  it('keeps at least one workspace visible, whatever the layout says', () => {
    const allHidden = {
      order: [...WORKSPACE_TABS],
      hidden: WORKSPACE_TABS.filter((tab) => !NON_HIDEABLE.includes(tab)),
    };
    expect(visibleTabs(normalizeLayout(allHidden, WORKSPACE_TABS), WORKSPACE_TABS).length).toBeGreaterThan(0);
  });
});

describe('buildNavSections', () => {
  // The rail's own inputs, one entry per tab, so the test exercises the real 17 rather
  // than a toy list that happens to work.
  const items = WORKSPACE_TABS.map((id) => ({ id }));

  it('keeps every item exactly once', () => {
    const out = buildNavSections(items).flatMap((s) => s.items);
    expect(out).toHaveLength(WORKSPACE_TABS.length);
    expect(new Set(out.map((i) => i.id)).size).toBe(WORKSPACE_TABS.length);
  });

  it('loses nothing when the groups change underneath it', () => {
    // The regrouping is the change; this is the assertion that the change is safe.
    const out = buildNavSections(items);
    const ids = out.flatMap((s) => s.items.map((i) => i.id)).sort();
    expect(ids).toEqual([...WORKSPACE_TABS].sort());
  });

  it('shows no empty section', () => {
    for (const section of buildNavSections(items)) {
      expect(section.items.length).toBeGreaterThan(0);
    }
  });

  it('puts ungrouped items in a trailing Ungrouped section rather than dropping them', () => {
    // A subset of groups, so some tabs are genuinely unplaced. The item must survive,
    // visibly — a nav item that disappears is the failure this function exists to stop.
    const sections = buildNavSections(items, [NAV_GROUPS[0]]);
    const ungrouped = sections.find((s) => s.label === 'Ungrouped');
    expect(ungrouped).toBeDefined();
    expect(sections.flatMap((s) => s.items)).toHaveLength(WORKSPACE_TABS.length);
  });

  it('emits no Ungrouped section when everything is placed', () => {
    expect(buildNavSections(items).some((s) => s.label === 'Ungrouped')).toBe(false);
  });

  it('preserves the group order it was given', () => {
    const reversed = [...NAV_GROUPS].reverse();
    const labels = buildNavSections(items, reversed).map((s) => s.label);
    expect(labels).toEqual([...reversed].map((g) => g.label));
  });

  it('carries extra item fields through untouched', () => {
    const withIcons = [{ id: 'risk' as const, label: 'Risk', icon: 'X' }];
    expect(buildNavSections(withIcons)[0].items[0].icon).toBe('X');
  });
});

describe('placement lookup', () => {
  it('finds the group for a known tab', () => {
    expect(unitIdOf('risk')).toBe('L18');
    expect(unitIdOf('markets')).toBe('L2');
  });

  it('returns undefined rather than throwing for an unknown tab', () => {
    // Deliberately cast: this is the behaviour a future editor needs when a tab has been
    // removed but a stale reference remains, and it must fail soft so the rail can skip it.
    expect(unitIdOf('nope' as never)).toBeUndefined();
  });

  it('types a group as an ArchitectureUnit', () => {
    const group: ArchitectureUnit | undefined = placementOf('execution');
    expect(group?.id).toBe('L20');
  });
});