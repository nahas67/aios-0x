import { describe, expect, it } from "vitest";
import { adaptSettingsV1, EMPTY_SETTINGS } from "./settings";

describe("settingsAdapter", () => {
  it("merges a partial server blob over neutral defaults and keeps the version", () => {
    const out = adaptSettingsV1({
      available: true,
      version: 4,
      settings: { autonomyLevel: "MANUAL", maxSlippageBps: 9 },
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out.version).toBe(4);
    expect(out.settings.autonomyLevel).toBe("MANUAL");
    expect(out.settings.maxSlippageBps).toBe(9);
    // Untouched keys fall back to neutral defaults, never to fake servers.
    expect(out.settings.defaultExecutionMode).toBe(EMPTY_SETTINGS.defaultExecutionMode);
    expect(out.settings.venues).toEqual([]);
  });

  it("accepts a legacy payload key tolerantly", () => {
    const out = adaptSettingsV1({
      available: true,
      version: 1,
      settings: {},
      payload: { autonomyLevel: "ASSISTED" },
    } as unknown as Parameters<typeof adaptSettingsV1>[0]);
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out.settings.autonomyLevel).toBe("ASSISTED");
  });

  it("branches on {available:false} with the server reason", () => {
    expect(adaptSettingsV1({ available: false, reason: "settings plane not wired" })).toEqual({
      unavailable: "settings plane not wired",
    });
  });
});
