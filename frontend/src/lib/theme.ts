/**
 * Runtime appearance: theme and accent. ADR-008.
 *
 * WHY THIS IS NOT A LIBRARY. The project admits no dependency without an ADR and has
 * exactly three required packages. Tailwind v4's `@theme` already emits CSS custom
 * properties, so switching is one attribute on `<html>` — there is nothing here a library
 * would do better, and adding one would have required an ADR to justify a wrapper around
 * `document.documentElement.dataset`.
 *
 * PERSISTENCE IS NOT A CREDENTIAL. The choice is stored in localStorage under
 * `aios.theme` / `aios.accent`, which is a deliberate distinction from the auth token:
 * that one is "kept in memory only — never written to browser storage"
 * (`stores/identity.ts`), and a colour preference is not a secret. Storing a preference
 * on the same footing as a bearer token would either weaken the token rule or lose the
 * preference; keeping them apart means neither is compromised.
 *
 * WHY THE ATTRIBUTES ARE APPLIED BEFORE FIRST PAINT. Appearance restored after React
 * mounts flashes the default palette first, which is the single most visible way a theme
 * system can look broken. `BOOTSTRAP` below is therefore also inlined into `index.html`
 * ahead of the stylesheet. It cannot import from the bundle, so there are two copies and
 * the only thing keeping them equal is this file's test.
 *
 * WHY ACCENT NAMES ARE SCREAMING_SNAKE, AND WHY THE UNION LIVES HERE. Appearance used to
 * be an `accentTheme` field on `SystemSettings`, so the union lived in `types.ts`. It was
 * removed: the backend never defined the field, so it rode along in every settings PUT as
 * an unknown key while the picker marked the form dirty for a change already on screen.
 * `AccentName` is now declared here, next to the CSS blocks and the persistence, and
 * `theme.test.ts` asserts `SystemSettings` does NOT carry it — otherwise the split-brain
 * would return quietly.
 */

/** A theme name must correspond to a `[data-theme]` block in `index.css`. */
export type ThemeName = 'dark-oled' | 'paper';

/** An accent name must correspond to a `[data-accent='…']` block in `index.css`. */
export type AccentName = 'CYAN' | 'EMERALD' | 'AMBER' | 'VIOLET';

/**
 * The default. `dark-oled` is what the console has always looked like, so a first-time
 * visitor sees no change; the alias exists because `index.html` also omits the attribute
 * on first paint, and an unnamed default would leave `data-theme` unset.
 */
export const DEFAULT_THEME: ThemeName = 'dark-oled';

/** The accent the console has always used; also the CSS default. */
export const DEFAULT_ACCENT: AccentName = 'CYAN';

export const THEMES: readonly ThemeName[] = ['dark-oled', 'paper'];
export const ACCENTS: readonly AccentName[] = ['CYAN', 'EMERALD', 'AMBER', 'VIOLET'];

const THEME_KEY = 'aios.theme';
const ACCENT_KEY = 'aios.accent';

export function isThemeName(value: unknown): value is ThemeName {
  return typeof value === 'string' && (THEMES as readonly string[]).includes(value);
}

export function isAccentName(value: unknown): value is AccentName {
  return typeof value === 'string' && (ACCENTS as readonly string[]).includes(value);
}

/**
 * The script inlined into `index.html` <head>, ahead of the stylesheet.
 *
 * Exported as a string so there is one definition of it. Both attributes are restored,
 * because they are independent axes: restoring the theme without the accent leaves the
 * console in a colour combination the operator never chose.
 *
 * Written to survive a throwing `getItem` rather than to catch around the whole body:
 * `t` and `a` simply stay `undefined`, and the ternaries below fall back to the defaults.
 * An empty catch that swallowed a DOM failure too would hide the one case that matters.
 */
export const BOOTSTRAP = `(function(){var d=document.documentElement,t,a;try{t=localStorage.getItem('${THEME_KEY}');a=localStorage.getItem('${ACCENT_KEY}');}catch(e){}d.dataset.theme=(t==='paper')?'paper':'${DEFAULT_THEME}';d.dataset.accent=(a==='EMERALD'||a==='AMBER'||a==='VIOLET')?a:'${DEFAULT_ACCENT}';})();`;

/**
 * Persisted theme, or the default.
 *
 * Every failure path returns the default rather than throwing: storage can be unavailable
 * (private mode, blocked cookies), and a console that cannot read a preference must still
 * render.
 */
export function readStoredTheme(): ThemeName {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return isThemeName(stored) ? stored : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

/** Persisted accent, or the default. Same storage caveat as `readStoredTheme`. */
export function readStoredAccent(): AccentName {
  try {
    const stored = window.localStorage.getItem(ACCENT_KEY);
    return isAccentName(stored) ? stored : DEFAULT_ACCENT;
  } catch {
    return DEFAULT_ACCENT;
  }
}

export function applyTheme(name: ThemeName): void {
  document.documentElement.dataset.theme = name;
  try {
    window.localStorage.setItem(THEME_KEY, name);
  } catch {
    // Preference is lost, theme still applied. Not worth surfacing to an operator.
  }
}

export function applyAccent(name: AccentName): void {
  document.documentElement.dataset.accent = name;
  try {
    window.localStorage.setItem(ACCENT_KEY, name);
  } catch {
    // As above: applied, just not remembered.
  }
}

/**
 * Applies appearance from the settings object in one call.
 *
 * The point of this being separate from `applyTheme`/`applyAccent` is that callers read
 * from `SystemSettings`, where the accent is persisted server-side but the theme is not —
 * so a caller that applied only the theme would silently drop the accent on reload.
 */
export function applyAppearance(theme: ThemeName, accent: AccentName): void {
  applyTheme(theme);
  applyAccent(accent);
}

/** Current theme as the DOM sees it, normalised in case the attribute was set by hand. */
export function currentTheme(): ThemeName {
  const attr = document.documentElement.dataset.theme;
  return isThemeName(attr) ? attr : DEFAULT_THEME;
}

/** Current accent, normalised. An unrecognised attribute falls back to the default. */
export function currentAccent(): AccentName {
  const attr = document.documentElement.dataset.accent;
  return isAccentName(attr) ? attr : DEFAULT_ACCENT;
}

/** The next theme in the list — for a single toggle control. */
export function nextTheme(name: ThemeName): ThemeName {
  const index = THEMES.indexOf(name);
  return THEMES[(index + 1) % THEMES.length] ?? DEFAULT_THEME;
}
