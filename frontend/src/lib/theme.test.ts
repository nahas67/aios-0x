/**
 * Appearance (theme + accent): persistence, fallback, and the anti-flash bootstrap.
 *
 * WHY THE DOM IS STUBBED BY HAND. Neither jsdom nor happy-dom is installed, and the
 * project admits no dependency without an ADR — so a DOM environment here would need a new
 * one. Stubbing is both cheaper and more precise: `lib/theme.ts` touches exactly two things
 * in the DOM, `window.localStorage` and `document.documentElement.dataset`, and a stub of
 * those two tests the real logic while making the module's actual browser surface explicit.
 *
 * The two checks that are not ordinary unit tests are at the bottom. Both exist because
 * the failure they guard is silent: a drifted bootstrap flashes on every load, and an
 * accent name with no matching CSS block repaints nothing and throws nothing.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  ACCENTS,
  BOOTSTRAP,
  DEFAULT_ACCENT,
  DEFAULT_THEME,
  THEMES,
  applyAccent,
  applyAppearance,
  applyTheme,
  currentAccent,
  currentTheme,
  isAccentName,
  isThemeName,
  nextTheme,
  readStoredAccent,
  readStoredTheme,
} from './theme';

/** A localStorage stand-in that can be made to throw, as a blocked or full store does. */
function makeStorage(throws = false) {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => {
      if (throws) throw new Error('storage unavailable');
      return map.get(key) ?? null;
    },
    setItem: (key: string, value: string) => {
      if (throws) throw new Error('quota exceeded');
      map.set(key, value);
    },
  };
}

let storageThrows = false;

function installDom() {
  storageThrows = false;
  const dataset: Record<string, string | undefined> = {};
  const storage = makeStorage(false);
  const g = globalThis as Record<string, unknown>;
  g.window = {
    get localStorage() {
      return storageThrows ? makeStorage(true) : storage;
    },
  };
  g.document = { documentElement: { dataset } };
}

beforeEach(installDom);

afterEach(() => {
  const g = globalThis as Record<string, unknown>;
  delete g.window;
  delete g.document;
});

describe('appearance names', () => {
  it('ships a dark default and a light alternative', () => {
    // Two themes minimum: one cannot demonstrate that switching works at all.
    expect(THEMES.length).toBeGreaterThanOrEqual(2);
    expect(DEFAULT_THEME).toBe('dark-oled');
    expect(THEMES).toContain('paper');
  });

  it('keeps the four accent presets the settings object already declared', () => {
    expect(ACCENTS).toEqual(['CYAN', 'EMERALD', 'AMBER', 'VIOLET']);
    expect(DEFAULT_ACCENT).toBe('CYAN');
  });

  it('recognises its own names and nothing else', () => {
    for (const theme of THEMES) expect(isThemeName(theme)).toBe(true);
    for (const bad of ['', 'dark', 'neon', null, undefined, 7, {}]) {
      expect(isThemeName(bad)).toBe(false);
    }
    for (const accent of ACCENTS) expect(isAccentName(accent)).toBe(true);
    // Lowercase must NOT pass: accent names are the settings union verbatim, and a
    // case-insensitive match here would let 'emerald' through to a `data-accent="emerald"`
    // that matches no CSS block and repaints nothing.
    for (const bad of ['emerald', 'cyan ', 'CYAN ', '', null, undefined, 7, {}]) {
      expect(isAccentName(bad)).toBe(false);
    }
  });
});

describe('reading stored appearance', () => {
  // No reset() call here: beforeEach(installDom) already installs a fresh document and
  // storage for every test in the file.
  it('falls back to the defaults with nothing stored', () => {
    expect(readStoredTheme()).toBe(DEFAULT_THEME);
    expect(readStoredAccent()).toBe(DEFAULT_ACCENT);
  });

  it('reads stored values', () => {
    window.localStorage.setItem('aios.theme', 'paper');
    window.localStorage.setItem('aios.accent', 'AMBER');
    expect(readStoredTheme()).toBe('paper');
    expect(readStoredAccent()).toBe('AMBER');
  });

  // A hand-edited or stale value must not become an unstyled console: an unknown
  // data-theme or data-accent matches no block, so every token falls back to nothing.
  it('ignores stored values that are not real names', () => {
    window.localStorage.setItem('aios.theme', 'neon-hacker');
    window.localStorage.setItem('aios.accent', 'chartreuse');
    expect(readStoredTheme()).toBe(DEFAULT_THEME);
    expect(readStoredAccent()).toBe(DEFAULT_ACCENT);
  });

  it('returns the defaults when storage throws', () => {
    storageThrows = true;
    expect(readStoredTheme()).toBe(DEFAULT_THEME);
    expect(readStoredAccent()).toBe(DEFAULT_ACCENT);
  });
});

describe('applying appearance', () => {
  it('sets each attribute and persists it', () => {
    applyTheme('paper');
    applyAccent('VIOLET');
    expect(document.documentElement.dataset.theme).toBe('paper');
    expect(document.documentElement.dataset.accent).toBe('VIOLET');
    expect(window.localStorage.getItem('aios.theme')).toBe('paper');
    expect(window.localStorage.getItem('aios.accent')).toBe('VIOLET');
  });

  it('still applies when persistence fails', () => {
    storageThrows = true;
    applyTheme('paper');
    applyAccent('AMBER');
    // The console must be themed even if the preference cannot be remembered.
    expect(document.documentElement.dataset.theme).toBe('paper');
    expect(document.documentElement.dataset.accent).toBe('AMBER');
  });

  it('round-trips through storage', () => {
    applyTheme('paper');
    applyAccent('EMERALD');
    expect(readStoredTheme()).toBe('paper');
    expect(readStoredAccent()).toBe('EMERALD');
  });

  // Theme and accent are independent axes, so applying one must not clear the other —
  // that would leave the console in a combination the operator never chose.
  it('applyAppearance sets both axes together', () => {
    applyAppearance('paper', 'EMERALD');
    expect(document.documentElement.dataset.theme).toBe('paper');
    expect(document.documentElement.dataset.accent).toBe('EMERALD');
  });

  it('changing one axis leaves the other untouched', () => {
    applyAppearance('paper', 'EMERALD');
    applyAccent('AMBER');
    expect(document.documentElement.dataset.theme).toBe('paper');
    expect(document.documentElement.dataset.accent).toBe('AMBER');
  });
});

describe('reading current appearance', () => {
  it('reads the applied values', () => {
    applyAppearance('paper', 'VIOLET');
    expect(currentTheme()).toBe('paper');
    expect(currentAccent()).toBe('VIOLET');
  });

  it('normalises unset or unknown attributes to the defaults', () => {
    expect(currentTheme()).toBe(DEFAULT_THEME);
    expect(currentAccent()).toBe(DEFAULT_ACCENT);
    document.documentElement.dataset.theme = 'not-a-theme';
    document.documentElement.dataset.accent = 'not-an-accent';
    expect(currentTheme()).toBe(DEFAULT_THEME);
    expect(currentAccent()).toBe(DEFAULT_ACCENT);
  });
});

describe('nextTheme', () => {
  it('cycles through every theme and returns to the start', () => {
    const visited = [DEFAULT_THEME];
    let cursor = DEFAULT_THEME;
    for (let i = 0; i < THEMES.length - 1; i += 1) {
      cursor = nextTheme(cursor);
      expect(THEMES).toContain(cursor);
      visited.push(cursor);
    }
    expect(nextTheme(cursor)).toBe(DEFAULT_THEME);
    expect(new Set(visited).size).toBe(THEMES.length);
  });
});

describe('the anti-flash bootstrap lives in index.html verbatim', () => {
  // Two copies means drift is possible, and the failure is a visible flash on every load.
  // Two levels up: this file is src/lib/theme.test.ts, so `..` is src/ and `../..` is the
  // frontend/ root where index.html lives.
  const html = readFileSync(resolve(__dirname, '..', '..', 'index.html'), 'utf-8');

  it('is inlined in index.html exactly as exported', () => {
    expect(html).toContain(BOOTSTRAP);
  });

  it('runs before the stylesheet can paint', () => {
    const scriptAt = html.indexOf(BOOTSTRAP);
    // Tailwind is imported from main.tsx, so the practical requirement is only that the
    // snippet is in <head>. Asserting it precedes </head> proves it is not deferred into
    // the body, which is where a flash would come from.
    expect(scriptAt).toBeGreaterThan(-1);
    expect(scriptAt).toBeLessThan(html.indexOf('</head>'));
  });

  it('carries no bundler-dependent syntax', () => {
    // It runs as a bare inline script, so it cannot use imports or arrow functions.
    expect(BOOTSTRAP).not.toMatch(/\bimport\b/);
    expect(BOOTSTRAP).not.toContain('=>');
  });

  it('restores both axes, not just the theme', () => {
    // A bootstrap that restores only the theme would drop the accent on every reload,
    // silently, which is exactly the half-wired behaviour this replaced.
    expect(BOOTSTRAP).toContain('dataset.theme');
    expect(BOOTSTRAP).toContain('dataset.accent');
    expect(BOOTSTRAP).toContain('aios.accent');
  });
});

describe('every appearance name has a CSS block', () => {
  // The failure this guards is silent. `data-accent="EMERALD"` with no matching block
  // repaints nothing and throws nothing, so typecheck, tests and build all pass while the
  // picker does nothing — which is precisely how the original accent picker shipped.
  // One level up: this file is src/lib/theme.test.ts, so `..` is src/, where index.css is.
  const css = readFileSync(resolve(__dirname, '..', 'index.css'), 'utf-8');

  it('every theme name has a [data-theme] block', () => {
    for (const theme of THEMES) {
      expect(css, `no [data-theme='${theme}'] block in index.css`).toContain(
        `[data-theme='${theme}']`,
      );
    }
  });

  // Matches a selector that has no `data-theme` qualifier, so the compound
  // `[data-theme='paper'][data-accent=…]` form cannot satisfy it. The first version used a
  // bare `toContain`, which reported "no block" for a preset that in fact had two — the
  // opposite of the intended check.
  it('every accent name has a [data-accent] block', () => {
    for (const accent of ACCENTS) {
      expect(
        new RegExp(`^\\[data-accent='${accent}'\\]\\s*\\{`, 'm').test(css),
        `no [data-accent='${accent}'] block in index.css`,
      ).toBe(true);
    }
  });

  it('accent blocks are defined for both themes', () => {
    // Theme and accent compose, so an accent defined for the dark theme only would put
    // dark tints under the paper theme.
    for (const accent of ACCENTS) {
      expect(css, `no paper variant for accent ${accent}`).toContain(
        `[data-theme='paper'][data-accent='${accent}']`,
      );
    }
  });
});

describe('appearance is not a server setting', () => {
  // `accentTheme` used to be a field on `SystemSettings`. The backend never defined it, so
  // it rode along in every settings PUT as an unknown key, and clicking a swatch marked the
  // form dirty — "unsaved changes" for a change already applied and on screen. Appearance
  // is client-local now, and these assertions stop the split-brain returning: re-adding the
  // field would give one preference two sources of truth, and neither would win clearly.
  const types = readFileSync(resolve(__dirname, '..', 'types.ts'), 'utf-8');
  const adapter = readFileSync(resolve(__dirname, '..', 'adapters', 'settings.ts'), 'utf-8');

  it('SystemSettings declares no accentTheme field', () => {
    expect(types).not.toMatch(/^\s*accentTheme\s*:/m);
  });

  it('the settings adapter does not carry one either', () => {
    expect(adapter).not.toMatch(/^\s*"?accentTheme"?\s*:/m);
  });
});
