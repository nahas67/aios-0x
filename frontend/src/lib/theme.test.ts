/**
 * Theme selection: persistence, fallback, and the anti-flash bootstrap.
 *
 * WHY THE DOM IS STUBBED BY HAND. Neither jsdom nor happy-dom is installed, and the
 * project admits no dependency without an ADR — so a DOM environment here would need a
 * new one. Stubbing is both cheaper and more precise: `lib/theme.ts` touches exactly two
 * things in the DOM, `window.localStorage` and `document.documentElement.dataset`, and a
 * stub of those two tests the real logic while making the module's actual browser surface
 * explicit. A full DOM emulation would prove more, of nothing this module does.
 *
 * The bootstrap is the part most likely to rot silently. It must run in `index.html`
 * before the stylesheet, because a theme applied after React mounts flashes the default
 * palette first — the most visible way a theme system can look broken. That means it
 * cannot import from the bundle, so there are inevitably two copies in the repo, and the
 * only thing keeping them equal is this test.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  DEFAULT_THEME,
  THEME_BOOTSTRAP,
  THEMES,
  applyTheme,
  currentTheme,
  isThemeName,
  nextTheme,
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
    clear: () => map.clear(),
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

describe('theme names', () => {
  it('ships a dark default and a light alternative', () => {
    // Two themes minimum: one cannot demonstrate that switching works at all.
    expect(THEMES.length).toBeGreaterThanOrEqual(2);
    expect(DEFAULT_THEME).toBe('dark-oled');
    expect(THEMES).toContain('paper');
  });

  it('recognises its own names and nothing else', () => {
    for (const theme of THEMES) expect(isThemeName(theme)).toBe(true);
    for (const bad of ['', 'dark', 'neon', null, undefined, 7, {}]) {
      expect(isThemeName(bad)).toBe(false);
    }
  });
});

describe('readStoredTheme', () => {
  // No reset() call here: beforeEach(installDom) already installs a fresh document and
  // storage for every test in the file, and leaving the old calls behind produced
  // `ReferenceError: reset is not defined` — which is the test file failing for a reason
  // that has nothing to do with the behaviour it claims to check.
  it('falls back to the default with nothing stored', () => {
    expect(readStoredTheme()).toBe(DEFAULT_THEME);
  });

  it('reads a stored theme', () => {
    window.localStorage.setItem('aios.theme', 'paper');
    expect(readStoredTheme()).toBe('paper');
  });

  // A hand-edited or stale value must not become an unstyled console: an unknown
  // data-theme matches no block, so every token falls back to nothing.
  it('ignores a stored value that is not a real theme', () => {
    window.localStorage.setItem('aios.theme', 'neon-hacker');
    expect(readStoredTheme()).toBe(DEFAULT_THEME);
  });

  it('returns the default when storage throws', () => {
    storageThrows = true;
    expect(readStoredTheme()).toBe(DEFAULT_THEME);
  });
});

describe('applyTheme', () => {
  it('sets the attribute and persists it', () => {
    applyTheme('paper');
    expect(document.documentElement.dataset.theme).toBe('paper');
    expect(window.localStorage.getItem('aios.theme')).toBe('paper');
  });

  it('still applies the theme when persistence fails', () => {
    storageThrows = true;
    applyTheme('paper');
    // The console must be themed even if the preference cannot be remembered.
    expect(document.documentElement.dataset.theme).toBe('paper');
  });

  it('round-trips through storage', () => {
    applyTheme('paper');
    expect(readStoredTheme()).toBe('paper');
  });
});

describe('currentTheme', () => {
  it('reads the applied theme', () => {
    applyTheme('paper');
    expect(currentTheme()).toBe('paper');
  });

  it('normalises an unset or unknown attribute to the default', () => {
    expect(currentTheme()).toBe(DEFAULT_THEME);
    document.documentElement.dataset.theme = 'not-a-theme';
    expect(currentTheme()).toBe(DEFAULT_THEME);
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
  // The whole point of exporting the snippet as a string is that index.html inlines it,
  // because it has to run before first paint and therefore cannot import from the bundle.
  // Two copies means drift is possible, and the failure is a visible flash on every load.
  // Two levels up: this file is src/lib/theme.test.ts, so `..` is src/ and `../..` is the
  // frontend/ root where index.html lives. One `..` resolves to src/index.html, which does
  // not exist — hence the explicit climb rather than a path that looks right and is not.
  const html = readFileSync(resolve(__dirname, '..', '..', 'index.html'), 'utf-8');

  it('is inlined in index.html exactly as exported', () => {
    expect(html).toContain(THEME_BOOTSTRAP);
  });

  it('runs before the stylesheet can paint', () => {
    const scriptAt = html.indexOf(THEME_BOOTSTRAP);
    // Tailwind is imported from main.tsx, so the practical requirement is only that the
    // snippet is in <head>. Asserting it precedes </head> is enough to prove it is not
    // deferred into the body, which is where a flash would come from.
    expect(scriptAt).toBeGreaterThan(-1);
    expect(scriptAt).toBeLessThan(html.indexOf('</head>'));
  });

  it('carries no bundler-dependent syntax', () => {
    // It runs as a bare inline script, so it cannot use imports or module syntax.
    expect(THEME_BOOTSTRAP).not.toMatch(/\bimport\b/);
    expect(THEME_BOOTSTRAP).not.toContain('=>');
  });
});