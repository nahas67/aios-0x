/**
 * The analyst console's workspaces placed against ARCHITECTURE.txt's own structure.
 *
 * WHY THIS IS NOT THE PLAN'S IA.
 *
 * The approved plan proposed eight groups named Observe / Reason / Certify / Decide /
 * Allocate / Authorize / Execute / Settle / Learn, and labelled them "the invented part"
 * — correctly, because §12 turns out to be a flow *diagram*, not a list of named stages.
 * Those eight names appear nowhere in the architecture. §12's actual text is a vertical
 * arrow chain from "BTC market event" to "Champion/Challenger statistics".
 *
 * What the architecture DOES have is §2's twenty-five named LAYER boxes, in causal order,
 * plus §3's six control planes. Those are the document's own structural units, so the
 * grouping is derived from them instead of invented alongside them. The plan's intent —
 * show the console in the order the system thinks — survives; its vocabulary does not, and
 * swapping invented names for the document's own is the whole difference between a claim
 * and a preference.
 *
 * NOT EVERY WORKSPACE IS A LAYER, and pretending otherwise would be the easy lie.
 *
 * Three of the seventeen do not belong to a layer at all:
 *
 *   - `models` and `system` are §3 control planes (Model Governance, Observability).
 *     §3 explicitly states its planes "cut across" the layers, so a control plane is not
 *     a layer and grouping it as one would be a category error.
 *   - `overview` and `trading` are genuinely cross-cutting. Verified by reading what they
 *     render, not inferred from their names: CommandCanvas mounts eight subsystems
 *     (capital trajectory, intelligence stream, allocation map, agent network, execution
 *     tape, regime field, provenance explorer, risk spectrum), and LiveTradingWorkspace
 *     spans market data through to the execution ticket. Neither is one layer.
 *   - `design_system` and `settings` are developer tooling and configuration. The
 *     architecture describes no unit for either, and inventing one to place them would
 *     be inventing structure to fit a layout.
 *
 * So placement has three kinds, and the difference is recorded per workspace rather than
 * flattened away: a layer, a control plane, or explicitly not architecture-derived.
 *
 * WHAT THIS FILE ALSO RECORDS: §2's twenty-five layers against the seventeen screens.
 * Several layers that the architecture treats as load-bearing have no workspace at all,
 * and that list is a finding, not an omission — see `LAYERS_WITHOUT_WORKSPACE`.
 */

import type { WorkspaceTab } from '../types';

/** How a workspace was placed, which is not the same thing for every one. */
export type Placement =
  /** §2 gives this workspace's subject its own layer. */
  | 'layer'
  /** §3 defines this as a control plane that cuts across layers. */
  | 'control-plane'
  /** No architecture unit describes it; grouped for navigation only. */
  | 'not-architecture-derived';

export interface ArchitectureUnit {
  /** `L2`, `§3B`, or a `x-` prefix for the non-architecture groups. */
  readonly id: string;
  readonly label: string;
  readonly placement: Placement;
  /** Tabs placed here, in the order they should appear. */
  readonly tabs: readonly WorkspaceTab[];
}

/**
 * §2's layers, transcribed from ARCHITECTURE.txt on 2026-10-02 and checked by
 * extraction rather than by hand: a grep for `LAYER \d+` returns exactly 25 matches.
 * `test_architecture_layers.test.ts` re-checks that count against the file itself is not
 * possible from the browser, so the count is pinned here and the names are pinned beside
 * it — if §2 gains a layer 26, the pinned count fails and forces a restatement.
 */
export const LAYERS = [
  { id: 'L1', label: 'Reference & Temporal Authority' },
  { id: 'L2', label: 'Data Truth Fabric' },
  { id: 'L3', label: 'Evidence Fabric' },
  { id: 'L4', label: 'Institutional Research' },
  { id: 'L5', label: 'Quant Research Factory' },
  { id: 'L6', label: 'Experiment Ledger' },
  { id: 'L7', label: 'Strategy Certification Firewall' },
  { id: 'L8', label: 'Feature Fabric' },
  { id: 'L9', label: 'Regime Intelligence' },
  { id: 'L10', label: 'Dual-Speed Intelligence' },
  { id: 'L11', label: 'Calibration & Selective Decision' },
  { id: 'L12', label: 'Certified Playbook Engine' },
  { id: 'L13', label: 'Robust Portfolio Brain' },
  { id: 'L14', label: 'Financial Truth' },
  { id: 'L15', label: 'Position Accounting' },
  { id: 'L16', label: 'Valuation' },
  { id: 'L17', label: 'Portfolio State Projection' },
  { id: 'L18', label: 'Deterministic Capital Firewall' },
  { id: 'L19', label: 'Capital Authorization' },
  { id: 'L20', label: 'Execution Kernel' },
  { id: 'L21', label: 'Execution Digital Twin' },
  { id: 'L22', label: 'Reconciliation' },
  { id: 'L23', label: 'Institutional Memory' },
  { id: 'L24', label: 'Governed Learning' },
  { id: 'L25', label: 'Champion / Challenger Arena' },
] as const;

/**
 * The navigation spine: units in §2's causal order, then §3's control planes, then the
 * groups that exist for navigation only.
 *
 * Only layers that actually have a screen appear. Listing all twenty-five would put
 * fourteen permanent empty headings in front of an operator, which is worse than the
 * gap it would document — so the absent layers are named in `LAYERS_WITHOUT_WORKSPACE`
 * where they are a finding rather than clutter.
 */
export const NAV_GROUPS: readonly ArchitectureUnit[] = [
  {
    id: 'x-system',
    label: 'System-wide',
    placement: 'not-architecture-derived',
    // Cross-cutting by inspection, not by name: see the module docstring.
    tabs: ['overview', 'trading'],
  },
  { id: 'L2', label: 'L2 · Data Truth Fabric', placement: 'layer', tabs: ['markets'] },
  { id: 'L3', label: 'L3 · Evidence Fabric', placement: 'layer', tabs: ['provenance'] },
  {
    id: 'L4',
    label: 'L4 · Institutional Research',
    placement: 'layer',
    tabs: ['research'],
  },
  {
    id: 'L7',
    label: 'L7 · Strategy Certification Firewall',
    placement: 'layer',
    // Layer 7's own screen, added in P5: the certification verdict, its checks, and
    // the reason any figure is refused. `strategies` sits here too but is NOT this —
    // it is strategy research, while Layer 7 is the gate deciding whether a strategy
    // may trade at all.
    tabs: ['strategies', 'certification'],
  },
  {
    id: 'L13',
    label: 'L13 · Robust Portfolio Brain',
    placement: 'layer',
    tabs: ['portfolio'],
  },
  { id: 'L14', label: 'L14 · Financial Truth', placement: 'layer', tabs: ['financial'] },
  {
    id: 'L15',
    label: 'L15 · Position Accounting',
    placement: 'layer',
    tabs: ['accounting'],
  },
  {
    id: 'L18',
    label: 'L18 · Deterministic Capital Firewall',
    placement: 'layer',
    tabs: ['risk'],
  },
  { id: 'L20', label: 'L20 · Execution Kernel', placement: 'layer', tabs: ['execution'] },
  { id: 'L22', label: 'L22 · Reconciliation', placement: 'layer', tabs: ['audit'] },
  { id: 'L24', label: 'L24 · Governed Learning', placement: 'layer', tabs: ['agents'] },
  { id: '§3B', label: '§3B · Model Governance', placement: 'control-plane', tabs: ['models'] },
  { id: '§3C', label: '§3C · Observability', placement: 'control-plane', tabs: ['system'] },
  {
    id: 'x-tooling',
    label: 'Tooling',
    placement: 'not-architecture-derived',
    tabs: ['design_system', 'settings'],
  },
];

/**
 * §2 layers with no workspace, and what that means.
 *
 * Not padding. Several of these are the load-bearing parts of the architecture:
 * L23 Institutional Memory is what §12's tail (`Memory → Counterfactual evaluation`)
 * depends on, and L25 Champion/Challenger Arena is the destination of that same chain.
 * A console that cannot show either is not showing the system the architecture describes.
 */
export const LAYERS_WITHOUT_WORKSPACE: readonly { id: string; label: string; note: string }[] =
  [
    {
      id: 'L1',
      label: 'Reference & Temporal Authority',
      note: 'Security master and corporate actions. No screen; likely deliberate for a system view.',
    },
    {
      id: 'L5',
      label: 'Quant Research Factory',
      note: 'Strategy research may cover this, but it is placed at L7 and not claimed here.',
    },
    {
      id: 'L6',
      label: 'Experiment Ledger',
      note: 'No screen. Experiments are the input to Champion/Challenger statistics.',
    },
    {
      id: 'L8',
      label: 'Feature Fabric',
      note: 'No screen. Its only consumer is the models that read features, so absence here may be correct rather than a gap — but that is a guess, not a finding.',
    },
    {
      id: 'L9',
      label: 'Regime Intelligence',
      note: 'Shown inside CommandCanvas as MarketRegimeField, not as a workspace of its own.',
    },
    {
      id: 'L10',
      label: 'Dual-Speed Intelligence',
      note: 'No screen. Two-speed inference has no operator-visible surface, so an operator cannot see which path answered.',
    },
    {
      id: 'L11',
      label: 'Calibration & Selective Decision',
      note: 'No screen. This is the layer that decides TRADE vs no-trade.',
    },
    {
      id: 'L12',
      label: 'Certified Playbook Engine',
      note: 'No screen. §12 names "Certified playbook found" as the precondition for any trade.',
    },
    {
      id: 'L16',
      label: 'Valuation',
      note: 'No screen of its own. Valuation output is most likely consumed by L13 and shown there, which would make this correct rather than missing.',
    },
    {
      id: 'L17',
      label: 'Portfolio State Projection',
      note: 'No screen. §12 makes this the state every downstream consumer reads.',
    },
    {
      id: 'L19',
      label: 'Capital Authorization',
      note: 'No screen, though `risk` sits at L18 and authorisation is the next step.',
    },
    {
      id: 'L21',
      label: 'Execution Digital Twin',
      note: 'No screen. A simulation twin is not on the §8 kill path, so its absence does not endanger the control plane — it only means execution cannot be rehearsed.',
    },
    {
      id: 'L23',
      label: 'Institutional Memory',
      note: 'No screen. §12 ends with Memory → Counterfactual evaluation → Champion/Challenger.',
    },
    {
      id: 'L25',
      label: 'Champion / Challenger Arena',
      note: 'No screen, and it is the terminus of §12. `promote_model` exists without a view.',
    },
  ];

/** Every tab, with the unit it was placed in. A tab in two units is a defect. */
export function placementOf(tab: WorkspaceTab): ArchitectureUnit | undefined {
  return NAV_GROUPS.find((group) => group.tabs.includes(tab));
}

/** The unit id a tab was placed in, or undefined when it was placed nowhere. */
export function unitIdOf(tab: WorkspaceTab): string | undefined {
  return placementOf(tab)?.id;
}

/**
 * Order a flat list of nav items into the §2 spine, preserving every item exactly once.
 *
 * This is the one piece of real logic the regrouping introduced, and it is the piece
 * where a bug is invisible: drop an item and the console simply has one fewer screen,
 * which nobody notices until they go looking for it. So it lives here, pure, rather than
 * inline in the rail where it cannot be tested — the frontend has no component-test
 * framework, which is the same reason `executiveReconcile` keeps its decisions in a lib.
 *
 * Generic over the item shape so the rail keeps ownership of its icons and badges while
 * this owns ordering. Anything the groups do not place lands in a trailing `Ungrouped`
 * section: visible, not silently dropped.
 */
export function buildNavSections<T extends { id: WorkspaceTab }>(
  items: readonly T[],
  groups: readonly ArchitectureUnit[] = NAV_GROUPS,
): { label: string; items: T[] }[] {
  const byTab = new Map(items.map((item) => [item.id, item]));
  const placedIds = new Set(groups.flatMap((group) => [...group.tabs]));
  const unplaced = items.filter((item) => !placedIds.has(item.id));

  return [
    ...groups
      .map((group) => ({
        label: group.label,
        items: group.tabs
          .map((tab) => byTab.get(tab))
          .filter((item): item is T => item !== undefined),
      }))
      .filter((section) => section.items.length > 0),
    ...(unplaced.length > 0 ? [{ label: 'Ungrouped', items: [...unplaced] }] : []),
  ];
}