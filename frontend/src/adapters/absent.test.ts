import { describe, expect, it } from "vitest";
import { isUnavailable, unavailableReason } from "./absent";

describe("absent", () => {
  it("detects {available:false} with reason", () => {
    expect(isUnavailable({ available: false, reason: "nope" })).toBe(true);
  });

  it("detects knowledge shape {available:false} with no reason key", () => {
    expect(isUnavailable({ available: false })).toBe(true);
    expect(unavailableReason({ available: false }, "fallback")).toBe("fallback");
  });

  it("detects models shape {available:false, models:[]}", () => {
    expect(isUnavailable({ available: false, models: [] })).toBe(true);
  });

  it("passes through live payloads", () => {
    expect(isUnavailable({ available: true, positions: [] })).toBe(false);
    expect(isUnavailable({ positions: [] })).toBe(false);
    expect(isUnavailable(null)).toBe(false);
  });

  it("prefers the server reason when present", () => {
    expect(unavailableReason({ available: false, reason: "r" }, "fb")).toBe("r");
  });
});
