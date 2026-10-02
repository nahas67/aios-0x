/**
 * Operator layout: which workspaces are visible, and in what order. Presentation only.
 *
 * WHAT THIS IS NOT, AND WHY IT SAYS SO LOUDLY
 * ===========================================
 * Hiding a workspace changes what an operator can SEE. It changes nothing about what the
 * system does. The risk firewall, the kill switch, RBAC and every control action live in the
 * backend and are unaffected by anything in this file.
 *
 * That distinction is the whole risk of this feature. A toggle labelled "hide Risk" sitting
 * in a trading console is one glance away from reading as "disable the risk controls", and an
 * operator who believed that reading would be badly misled by a UI affordance. So the type
 * is named `WorkspaceLayout`, the field is `hidden` rather than `disabled`, and the panel
 * that edits it states the boundary in plain words rather than leaving it to be inferred.
 *
 * WHY NORMALISATION IS THE INTERESTING PART
 * ==========================================
 * A saved layout is a snapshot of the tab list at the moment it was saved. Tabs are ADDED —
 * `chat` and `certification` both arrived that way. A naive restore would then hide or
 * mis-order workspaces that did not exist when the layout was written, and an operator would
 * return to a console that has quietly lost a screen with no way to tell which.
 *
 * So `normalizeLayout` is total: it drops ids that no longer exist, appends ones that were
 * added since, de-duplicates, and preserves the relative order of everything it kept. A
 * stored layout can never remove a workspace from the console, only from the operator's own
 * list of things they chose to show — and even that is checked against the live tab list on
 * every read.
 *
 * Pure and DOM-free apart from the three persistence helpers at the bottom, which exist for
 * the same reason `theme.ts` does: a colour or layout preference is not a credential, and
 * the auth token stays memory-only.
 */

import type { WorkspaceTab } from '../types';

export interface WorkspaceLayout {
  /** Display order. Always a permutation of the live tab list after normalisation. */
  readonly order: readonly WorkspaceTab[];
  /** Tabs the operator chose to hide. Never affects enforcement. */
  readonly hidden: readonly WorkspaceTab[];
}

export const LAYOUT_STORAGE_KEY = 'aios.layout';

/** The architecture's order, which is also the default. */
export function defaultLayout(tabs: readonly WorkspaceTab[]): WorkspaceLayout {
  return { order: [...tabs], hidden: [] };
}

/**
 * Workspaces that cannot be hidden.
 *
 * `settings` holds the layout editor. Allowing it to be hidden strands the operator: the
 * control that would restore their navigation lives behind the navigation they just removed,
 * with no other route back. That is a one-way door created by a cosmetic toggle, which is
 * the worst ratio of harm to intent available in this whole feature.
 *
 * So the constraint is enforced in the LOGIC, not in the button's disabled state — a
 * disabled button is a UI convention, and `normalizeLayout` has to undo a stored layout that
 * hid it anyway, because an operator on an older build could have saved exactly that.
 */
export const NON_HIDEABLE: readonly WorkspaceTab[] = ['settings'];

export function canHide(tab: WorkspaceTab): boolean {
  return !NON_HIDEABLE.includes(tab);
}

/**
 * Coerce anything — a stale payload, a hand-edited value, a shape from a future version —
 * into a layout that is safe to render.
 *
 * Total by construction. Three failure modes are handled explicitly, and each is a way a
 * saved layout could otherwise damage the console:
 *
 *   1. ids that no longer exist        -> dropped (a removed tab cannot linger)
 *   2. ids added since the layout      -> appended in architecture order (nothing is lost)
 *   3. duplicates in the stored order  -> first occurrence kept (a tab cannot appear twice)
 *
 * A layout is restored on every page load, so any of these would be a persistent, silent
 * degradation rather than a one-off glitch.
 */
/**
 * Canonical `hidden` ordering: by display order.
 *
 * Applied on EVERY path that produces a layout, not just on the setter. It exists so that
 * two layouts meaning the same thing compare equal — otherwise the stored value churns
 * between reads on ordering alone, and a stable layout keeps rewriting localStorage.
 */
function sortByOrder(entries: readonly WorkspaceTab[], order: readonly WorkspaceTab[]): WorkspaceTab[] {
  const rank = new Map(order.map((entry, index) => [entry, index]));
  return [...entries].sort((a, b) => (rank.get(a) ?? Number.MAX_SAFE_INTEGER) - (rank.get(b) ?? Number.MAX_SAFE_INTEGER));
}

export function normalizeLayout(raw: unknown, tabs: readonly WorkspaceTab[]): WorkspaceLayout {
  const known = new Set<string>(tabs);
  const fallbackOrder = [...tabs];

  const candidate = (raw ?? {}) as { order?: unknown; hidden?: unknown };
  const storedOrder = Array.isArray(candidate.order) ? candidate.order : [];
  const storedHidden = Array.isArray(candidate.hidden) ? candidate.hidden : [];

  const seen = new Set<string>();
  const order: WorkspaceTab[] = [];
  for (const entry of storedOrder) {
    if (typeof entry !== 'string' || !known.has(entry) || seen.has(entry)) continue;
    seen.add(entry);
    order.push(entry as WorkspaceTab);
  }
  // Anything the stored order did not mention keeps its architecture position, appended
  // rather than interleaved: guessing where a new tab "belongs" would scramble an order the
  // operator deliberately set.
  for (const tab of fallbackOrder) {
    if (!seen.has(tab)) order.push(tab);
  }

  const hidden: WorkspaceTab[] = [];
  for (const entry of storedHidden) {
    if (typeof entry !== 'string' || !known.has(entry) || hidden.includes(entry as WorkspaceTab)) continue;
    // Defence in depth: a stored layout that hid a non-hideable workspace is corrected on
    // read, not merely prevented on write. Otherwise the only way out would be a build.
    if (!canHide(entry as WorkspaceTab)) continue;
    hidden.push(entry as WorkspaceTab);
  }

  return { order, hidden: sortByOrder(hidden, order) };
}

/** Visible tabs in the operator's order. */
export function visibleTabs(layout: WorkspaceLayout, tabs: readonly WorkspaceTab[]): WorkspaceTab[] {
  const hidden = new Set(layout.hidden.filter((tab) => canHide(tab)));
  return normalizeLayout(layout, tabs).order.filter((tab) => !hidden.has(tab));
}

/** Move a tab by one position, clamped at the ends. A no-op move returns the same layout. */
export function moveTab(layout: WorkspaceLayout, tab: WorkspaceTab, delta: number): WorkspaceLayout {
  const order = [...layout.order];
  const from = order.indexOf(tab);
  if (from === -1) return layout;
  const to = Math.min(order.length - 1, Math.max(0, from + delta));
  if (to === from) return layout;
  order.splice(to, 0, ...order.splice(from, 1));
  return { ...layout, order };
}

/** Show or hide. Idempotent, and hiding something already hidden is not an error. */
export function setHidden(
  layout: WorkspaceLayout,
  tab: WorkspaceTab,
  hidden: boolean,
): WorkspaceLayout {
  if (!canHide(tab)) return layout;
  const next = layout.hidden.filter((entry) => entry !== tab);
  if (hidden) next.push(tab);
  return { ...layout, hidden: sortByOrder(next, layout.order) };
}

export function isHidden(layout: WorkspaceLayout, tab: WorkspaceTab): boolean {
  // Never reports a non-hideable workspace as hidden, even for a layout that claims it is.
  // The rail asks this before deciding what to draw.
  return canHide(tab) && layout.hidden.includes(tab);
}

/**
 * How many workspaces the operator has hidden.
 *
 * Counts `layout.hidden` directly. The first version normalised first, and normalisation
 * filters against the live tab list — so passing an empty list here silently returned 0 for
 * every layout, which is the kind of wrong-but-plausible number that gets shipped.
 */
export function hiddenCount(layout: WorkspaceLayout): number {
  return layout.hidden.length;
}

/** Is the layout still the one the operator started with? */
export function isDefault(layout: WorkspaceLayout, tabs: readonly WorkspaceTab[]): boolean {
  const normalized = normalizeLayout(layout, tabs);
  return (
    normalized.order.length === tabs.length &&
    normalized.order.every((tab, index) => tab === tabs[index]) &&
    normalized.hidden.length === 0
  );
}

// --------------------------------------------------------------------------------------
// Persistence. A layout preference is not a credential; the auth token stays memory-only.
// --------------------------------------------------------------------------------------

export function readStoredLayout(tabs: readonly WorkspaceTab[]): WorkspaceLayout {
  try {
    const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (!raw) return defaultLayout(tabs);
    return normalizeLayout(JSON.parse(raw), tabs);
  } catch {
    // Unavailable storage, malformed JSON, a value from a future version: all mean "use the
    // default" rather than "fail to load the console".
    return defaultLayout(tabs);
  }
}

export function applyLayout(layout: WorkspaceLayout): void {
  try {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout));
  } catch {
    // The layout applies for this session even if it cannot be remembered.
  }
}
