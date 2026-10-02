/**
 * Layout controls: reorder and hide workspaces. Presentation only.
 *
 * WHY THE BANNER IS NOT DECORATION
 * ================================
 * A toggle labelled "hide Risk" in a trading console is one glance from reading as "disable
 * the risk controls". An operator who believed that reading would be misled by an
 * affordance, and the harm would be theirs, not the system's — enforcement is entirely
 * server-side and nothing in this panel reaches it.
 *
 * So the boundary is stated in the panel, in plain words, at the top: hiding removes a
 * workspace from YOUR navigation and changes nothing about what the system enforces. That
 * sentence is the feature's actual safety requirement. Everything below it is mechanics.
 *
 * WHY UP/DOWN BUTTONS RATHER THAN DRAG
 * =====================================
 * Reordering by drag needs no dependency here but is keyboard-inaccessible and awkward to
 * test; two buttons and a hidden toggle are operable from the keyboard, announced correctly,
 * and assertable without a DOM emulation — which matters, because this repo has no jsdom.
 * There is no `<StateView>`-style abstraction to lean on here: the interesting logic is in
 * `lib/layout.ts`, which is pure and tested directly.
 *
 * HIDING SOMETHING ACTIVE. If the operator hides the workspace they are currently in, the
 * console moves them to the first visible tab rather than rendering nothing. An empty console
 * with a working navigation is the same silent-degradation failure this whole feature has to
 * avoid.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { ArrowUp, ArrowDown, Eye, EyeOff, RotateCcw, TriangleAlert } from 'lucide-react';
import {
  applyLayout,
  canHide,
  defaultLayout,
  hiddenCount,
  isDefault,
  isHidden,
  moveTab,
  normalizeLayout,
  readStoredLayout,
  setHidden,
  type WorkspaceLayout,
} from '../lib/layout';
import type { WorkspaceTab } from '../types';

/** Human labels for the rail order. Falls back to the id, so a new tab is never blank. */
const LABELS: Partial<Record<WorkspaceTab, string>> = {
  overview: 'Overview',
  trading: 'Live Trading',
  portfolio: 'Portfolio',
  markets: 'Markets',
  research: 'Research',
  agents: 'Agents',
  strategies: 'Strategies',
  certification: 'Certification',
  execution: 'Execution',
  risk: 'Risk & Firewall',
  models: 'Model Governance',
  provenance: 'Provenance',
  accounting: 'Accounting & Tax',
  financial: 'Financial Kernel',
  audit: 'Audit & Integrity',
  system: 'System Health',
  chat: 'Operator Chat',
  design_system: 'Design System',
  settings: 'Settings',
};

/**
 * Workspaces whose hiding is more likely to be misread as disabling something.
 * Not a restriction — they can still be hidden — but the row says so out loud, because
 * "hide Risk" next to a firewall icon is exactly the pairing that invites the wrong reading.
 */
const GUARD_WORKSHOPS: readonly WorkspaceTab[] = ['risk', 'execution', 'audit', 'certification'];

export default function LayoutPanel({
  tabs,
  activeTab,
  onLayoutChange,
}: {
  tabs: readonly WorkspaceTab[];
  activeTab: WorkspaceTab;
  /** Reported so the caller can relocate the operator if they hide what they are in. */
  onLayoutChange: (layout: WorkspaceLayout) => void;
}): React.ReactElement {
  const [layout, setLayout] = useState<WorkspaceLayout>(() => normalizeLayout(readStoredLayout(tabs), tabs));

  // A tab added between mount and now (or a changed tab list) must not be dropped: the
  // layout is re-normalised against the live list rather than trusted as stored.
  useEffect(() => {
    setLayout((prev) => {
      const next = normalizeLayout(prev, tabs);
      return next.order.length === prev.order.length && next.hidden.length === prev.hidden.length ? prev : next;
    });
  }, [tabs]);

  const update = useCallback(
    (next: WorkspaceLayout) => {
      setLayout(next);
      applyLayout(next);
      onLayoutChange(next);
    },
    [onLayoutChange],
  );

  const toggle = useCallback(
    (tab: WorkspaceTab) => update(setHidden(layout, tab, !isHidden(layout, tab))),
    [layout, update],
  );

  const nudge = useCallback(
    (tab: WorkspaceTab, delta: number) => update(moveTab(layout, tab, delta)),
    [layout, update],
  );

  const reset = useCallback(() => update(defaultLayout(tabs)), [tabs, update]);

  return (
    <div className="p-4 rounded bg-surface-veil border border-border-subtle space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="font-bold text-text-strong text-xs uppercase tracking-wider">
          Workspace Layout
        </div>
        <button
          type="button"
          onClick={reset}
          disabled={isDefault(layout, tabs)}
          className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider border border-border-subtle bg-surface-sunken text-text-muted hover:text-text-strong disabled:opacity-40"
        >
          <RotateCcw className="w-3 h-3" aria-hidden />
          Reset
        </button>
      </div>

      {/* The safety requirement, stated as the first thing in the panel. */}
      <div className="flex items-start gap-2 px-2.5 py-2 rounded bg-info-bg border border-accent">
        <TriangleAlert className="w-3.5 h-3.5 mt-0.5 shrink-0 text-accent" aria-hidden />
        <p className="text-[10px] text-text-muted leading-relaxed">
          This changes your navigation only. <span className="text-text-strong">Hiding a workspace does not
          disable it</span> — the risk firewall, the kill switch, RBAC and every control action run in the
          backend regardless of what is shown here.
          {hiddenCount(layout) > 0 && (
            <>
              {' '}Currently hidden: <span className="text-text-strong">{hiddenCount(layout)}</span>.
            </>
          )}
        </p>
      </div>

      <ol className="space-y-1">
        {layout.order.map((tab, index) => {
          const hidden = isHidden(layout, tab);
          const guard = GUARD_WORKSHOPS.includes(tab);
          return (
            <li
              key={tab}
              className={`flex items-center gap-2 px-2 py-1.5 rounded border ${
                hidden
                  ? 'bg-surface-sunken border-border-faint opacity-70'
                  : 'bg-surface-raised border-border-subtle'
              }`}
            >
              <span className="w-4 text-[9px] font-mono text-text-subtle text-right">{index + 1}</span>
              <span className={`text-xs flex-1 min-w-0 truncate ${hidden ? 'text-text-dim line-through' : 'text-text-strong'}`}>
                {LABELS[tab] ?? tab}
                {guard && (
                  <span className="ml-1.5 text-[9px] uppercase tracking-wider text-warning border border-warning px-1">
                    enforced
                  </span>
                )}
              </span>

              <button
                type="button"
                onClick={() => nudge(tab, -1)}
                disabled={index === 0}
                aria-label={`Move ${LABELS[tab] ?? tab} up`}
                className="p-1 rounded border border-border-subtle bg-surface-sunken text-text-muted hover:text-text-strong disabled:opacity-30"
              >
                <ArrowUp className="w-3 h-3" aria-hidden />
              </button>
              <button
                type="button"
                onClick={() => nudge(tab, 1)}
                disabled={index === layout.order.length - 1}
                aria-label={`Move ${LABELS[tab] ?? tab} down`}
                className="p-1 rounded border border-border-subtle bg-surface-sunken text-text-muted hover:text-text-strong disabled:opacity-30"
              >
                <ArrowDown className="w-3 h-3" aria-hidden />
              </button>
              <button
                type="button"
                onClick={() => toggle(tab)}
                disabled={!canHide(tab)}
                title={
                  canHide(tab)
                    ? undefined
                    : 'Settings holds the layout editor — hiding it would remove the only control that restores your navigation.'
                }
                aria-pressed={hidden}
                aria-label={hidden ? `Show ${LABELS[tab] ?? tab}` : `Hide ${LABELS[tab] ?? tab}`}
                className={`flex items-center gap-1 px-1.5 py-1 rounded text-[10px] font-bold border ${
                  hidden
                    ? 'border-positive text-positive bg-positive-bg'
                    : 'border-border-subtle bg-surface-sunken text-text-muted hover:text-text-strong'
                } disabled:opacity-40 disabled:cursor-not-allowed`}
              >
                {hidden ? <Eye className="w-3 h-3" aria-hidden /> : <EyeOff className="w-3 h-3" aria-hidden />}
                {hidden ? 'Show' : 'Hide'}
              </button>
            </li>
          );
        })}
      </ol>

      {isHidden(layout, activeTab) && (
        <p className="text-[10px] text-warning">
          You are hiding the workspace you are currently in. The console will move you to the first
          visible one.
        </p>
      )}
    </div>
  );
}
