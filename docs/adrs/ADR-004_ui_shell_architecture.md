# ADR-004: Command-Center UI Architecture

## Context

The directive requires a minimalist-surface / deep-control institutional
interface across ~15 workspaces. Constraints: zero-build-step stack (stdlib
HTTP server + static HTML), single developer, existing JSON API, and a hard
rule against fake data.

## Decision

1. **Keep the zero-dependency SPA shell**: one static `ui/index.html` (vanilla
   JS, no framework, no bundler) consuming the JSON API. Rejected framework
   options (React/Next/Tailwind build chain) — they add a node toolchain and
   CI surface for zero functional gain at current scale; revisit only if the
   UI team grows or real-time charting demands it.
2. **Design tokens** grounded in the ui-ux-pro-max design-system run
   (Dark-OLED institutional: #020617 bg, slate panels, #22c55e positive /
   #ef4444 destructive, Fira Code/Fira Sans, dense 8px scale, subtle motion,
   reduced-motion honored).
3. **App shell**: fixed top status bar (state pills, global search, expert
   toggle, autonomy selector, kill switch) + grouped left navigation
   (COMMAND / INTELLIGENCE / OPERATIONS / SYSTEM) + per-workspace sections.
4. **Progressive disclosure**: Level-1 summary tables/cards everywhere;
   decision workspace drawer with Evidence → Agent Trace → Raw JSON → Audit
   toggles; settings accordion with expert-mode raw config.
5. **Real data only**: every workspace maps to an existing endpoint; missing
   capabilities render honest empty states (Strategies workspace ships as a
   documented empty state until a strategy registry exists).
6. **New read endpoints** (positions, portfolio, orders, agents,
   opportunities, events, regimes, audit-search) added as thin views over
   existing state — no new subsystems.

## Status

SUPERSEDED by [ADR-008](ADR-008_supersede_adr004_ui_shell_and_tokens.md) — 2026-10-02.

Decision 1 (keep the zero-dependency vanilla SPA, reject React/Next/Tailwind) was
**reversed**: the repository now runs React 19 + Vite + Tailwind v4 with a two-entry
build, because the scale conditions under which this ADR declined the build chain no
longer hold.

Decision 2 (design tokens) was **never implemented** and is now adopted through
[ADR-008](ADR-008_supersede_adr004_ui_shell_and_tokens.md), using the shipped palette
rather than this ADR's aspirational one so that adoption causes no visual regression.

Retained as the record of what was decided and why.

## Consequences

+ Instant iteration, no build step, auditor-friendly (view-source = whole UI).
+ All workspaces consume the same audited store the backend trusts.
− No component reuse across future native clients (acceptable: API is the
  contract).
− Single-file UI will split into modules if it exceeds ~1500 lines.

## Compliance

- 14/14 endpoints verified 200 live; workspaces verified populated.
- Accessibility: focus-visible rings, aria-labels on icon controls, semantic
  tables, status conveyed by text badges (not color alone), reduced-motion
  honored, keyboard shortcuts (/ focus search, Esc close).
