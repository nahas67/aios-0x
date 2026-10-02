/**
 * Runtime theme selection. ADR-008.
 *
 * WHY THIS IS NOT A LIBRARY. The project admits no dependency without an ADR and has
 * exactly three required packages. Tailwind v4's `@theme` already emits CSS custom
 * properties, so switching a theme is one attribute on `<html>` — there is nothing here
 * that a library would do better, and adding one would have required an ADR to justify a
 * wrapper around `document.documentElement.dataset`.
 *
 * PERSISTENCE IS NOT A CREDENTIAL. The choice is stored in localStorage under
 * `aios.theme`, which is a deliberate distinction from the auth token: that one is
 * "kept in memory only — never written to browser storage" (`stores/identity.ts`), and a
 * colour preference is not a secret. Storing a theme on the same footing as a bearer token
 * would either weaken the token rule or lose the preference; keeping them apart means
 * neither is compromised.
 *
 * WHY THE ATTRIBUTE IS APPLIED BEFORE FIRST PAINT. A theme restored after React mounts
 * flashes the default palette first, which is the single most visible way a theme system
 * can look broken. `readStoredTheme()` is therefore also called from `index.html` as an
 * inline script, before the stylesheet is applied — see `THEME_BOOTSTRAP` below, which is
 * duplicated verbatim there so both paths cannot drift.
 */

/** A theme name must correspond to a `[data-theme]` block in `index.css`. */
export type ThemeName = 'dark-oled' | 'paper';

/**
 * The default. `dark-oled` is what the console has always looked like, so a first-time
 * visitor sees no change; the alias exists because `index.html` also omits the attribute
 * on first paint, and an unnamed default would leave `data-theme` unset.
 */
export const DEFAULT_THEME: ThemeName = 'dark-oled';

export const THEMES: readonly ThemeName[] = ['dark-oled', 'paper'];

const STORAGE_KEY = 'aios.theme';

export function isThemeName(value: unknown): value is ThemeName {
  return typeof value === 'string' && (THEMES as readonly string[]).includes(value);
}

/**
 * The script inlined into `index.html` <head>, ahead of the stylesheet.
 *
 * Exported as a string so there is one definition of it. It has to run before first paint
 * to avoid a flash, which means it cannot import from the bundle — so the alternative
 * would have been a second hand-written copy in the HTML, and the two would drift. This
 * file's test asserts the HTML actually contains this exact text.
 */
export const THEME_BOOTSTRAP = `(function(){try{var t=localStorage.getItem('${STORAGE_KEY}');document.documentElement.dataset.theme=(t==='paper')?'paper':'${DEFAULT_THEME}';}catch(e){document.documentElement.dataset.theme='${DEFAULT_THEME}';}})();`;

/**
 * Persisted theme, or the default.
 *
 * Every failure path returns the default rather than throwing: storage can be unavailable
 * (private mode, blocked cookies), and a console that cannot read a preference must still
 * render.
 */
export function readStoredTheme(): ThemeName {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isThemeName(stored) ? stored : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function applyTheme(name: ThemeName): void {
  document.documentElement.dataset.theme = name;
  try {
    window.localStorage.setItem(STORAGE_KEY, name);
  } catch {
    // Preference is lost, theme still applied. Not worth surfacing to an operator.
  }
}

/** Current theme as the DOM sees it, normalised in case the attribute was set by hand. */
export function currentTheme(): ThemeName {
  const attr = document.documentElement.dataset.theme;
  return isThemeName(attr) ? attr : DEFAULT_THEME;
}

/** The next theme in the list — for a single toggle control. */
export function nextTheme(name: ThemeName): ThemeName {
  const index = THEMES.indexOf(name);
  return THEMES[(index + 1) % THEMES.length] ?? DEFAULT_THEME;
}