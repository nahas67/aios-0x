# ADR-008: Supersede ADR-004 — adopt the React/Vite/Tailwind shell, and finally build the token layer it specified

## Context

`ADR-004` (ACCEPTED, 2026-08-23) decided the Command-Center UI architecture. Two of its
decisions no longer describe this repository, and nothing has superseded it.

**Decision 1 is contradicted by the tree.** It decided:

> **Keep the zero-dependency SPA shell**: one static `ui/index.html` (vanilla JS, no
> framework, no bundler) consuming the JSON API. Rejected framework options
> (React/Next/Tailwind build chain) — they add a node toolchain and CI surface for zero
> functional gain at current scale.

The repository runs **React 19 + Vite + Tailwind v4** in `frontend/`, builds to `ui/dist`
via a two-entry Vite build, and has a CI job for frontend typecheck and build. The
rejection has already happened in fact; ADR-004 still forbids it in writing. An ACCEPTED
decision that contradicts the code it governs is worse than no decision, because a reader
cannot tell whether the code drifted or the record did.

**Decision 2 was never implemented, and it is the reason the UI cannot be themed.**
ADR-004 specified design tokens:

> Dark-OLED institutional: `#020617` bg, slate panels, `#22c55e` positive / `#ef4444`
> destructive, Fira Code/Fira Sans, dense 8px scale, subtle motion, reduced-motion honored.

Measured in `frontend/src`: **0 uses of `var(--…)`** and **206 hex literals across 43
files, 37 distinct values**. `index.css` declares `:root` custom properties
(`--bg-dark`, `--panel-dark`, `--accent-cyan`, …) that nothing consumes — even its own
`body` rule hardcodes `#08090d` instead of using the variable it just declared.

So there is no token layer. Recolouring the console today means editing 206 literals by
hand, which is the change that silently diverges between two screens. This is not a
missing feature; it is a missing substrate.

## Decision

**Supersede ADR-004.** This ADR records the framework reversal and adopts its token
decision, which had been correct in intent and skipped in practice.

1. **The shell is React + Vite + Tailwind v4.** ADR-004's rejection is reversed. The
   reasoning for the reversal is that the premise changed: the project now has real-time
   charting, an SSE stream, an isolated §8 operator surface requiring a *second build
   entry*, and 17 workspaces — the "zero functional gain at current scale" condition under
   which ADR-004 declined the build chain no longer holds.

2. **Tailwind v4's CSS-first `@theme` is the token layer.** No JavaScript token runtime
   and no new dependency: `@theme` emits CSS custom properties, which means a theme switch
   is a `:root` override with no rebuild. This satisfies the three-dependency rule without
   an ADR of its own, because it adds nothing to `pyproject.toml`.

3. **The shipped palette is the default, not ADR-004's.** Surface values are taken from the
   running UI (`#08090d` page, `#0d0f17` panel — the latter appearing 93 times, so it is
   the console's dominant surface) so that adopting tokens causes **zero visual
   regression**. ADR-004's *semantic* decisions are adopted: positive/destructive as
   green/red, a dense spacing scale, monospace for numerals.

4. **Tokens are the only place a colour literal may appear.** `rg '#[0-9a-fA-F]{6}'
   frontend/src --glob '!index.css'` must return zero. That is the gate, and it is
   mechanical rather than a matter of review taste.

5. **Runtime themes are CSS-only and non-secret.** Themes are `[data-theme]` attribute
   blocks. The active theme persists in `localStorage`, which is explicitly *not* the same
   class of data as the auth token — that one is memory-only by deliberate decision in
   `stores/identity.ts`, and a colour preference is not a credential.

6. **The §8 operator surface receives the same tokens and nothing else.** Theming must not
   widen the operator bundle, so `scripts/verify_operator_isolation.py` stays green
   throughout and is re-run at every phase.

7. **Customization is presentation-only.** It cannot alter RBAC, disable the kill switch,
   or change what the backend is permitted to do. The agent-facing chat
   (`ADR-008`'s companion, implemented separately) is likewise advisory: it may not place,
   cancel or authorise anything.

## Status

- **State**: ACCEPTED
- **Date**: 2026-10-02
- **Authors**: AIOS System Architecture Team
- **Supersedes**: ADR-004

## Consequences

### Positive Consequences

- A standing ACCEPTED decision no longer contradicts the code.
- The console becomes themeable, and runtime-switchable with no rebuild and no dependency.
- A mechanical gate replaces a review opinion: colour drift becomes a failing test rather
  than something a reviewer has to notice.
- The dead `:root` declarations in `index.css` are either adopted or deleted, so the file
  stops asserting things the code does not do.
- The 37 ad-hoc values collapse into a named scale, which is the precondition for the
  "more professional" judgement — a theme makes the UI configurable; it does not by itself
  make it better.

### Negative Consequences / Trade-offs

- Touching 206 literals across 43 files is a wide diff in files this ADR did not otherwise
  touch. Mitigated by the hex-literal gate plus `tsc` and vitest on every phase, so a
  migration that breaks a workspace fails rather than passing quietly.
- Tailwind v4's `@theme` is CSS-first, which is a different authoring model from the v3
  `tailwind.config.js` some prior knowledge assumes. It is already in use here.
- ADR-004's specific colours (`#020617`) are **not** adopted, so this ADR is a partial
  adoption of its token decision. Recorded deliberately: the shipped palette wins over the
  aspirational one to avoid a change that alters every screen on day one.

## Compliance & Verification

- `rg '#[0-9a-fA-F]{6}' frontend/src --glob '!index.css'` → **zero hits**.
- `rg -c 'var\(--' frontend/src` → **non-zero** (currently 0), proving the tokens are live
  rather than declared and ignored, which is the specific failure ADR-004 decision 2 had.
- `python scripts/verify_operator_isolation.py` → green (§8 surface unchanged by theming).
- `tsc -b --noEmit`, `vitest run`, `vite build`, `ruff check .`, and the documented mypy
  gate all stay green.
- `scripts/verify_current_architecture.py` stays green; it parses published figures from
  `CURRENT_ARCHITECTURE.md`, which this ADR does not change.
- Switching `data-theme` changes rendered colour with **no rebuild** — demonstrated by two
  shipped themes, since one theme proves nothing.
- Body-text contrast ≥ 4.5:1 in **both** themes.
- `pyproject.toml` required dependencies remain exactly 3.