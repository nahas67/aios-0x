import { describe, expect, it } from "vitest";
import { adaptRisk } from "./risk";
import type { RiskState } from "../api/types";

const risk: RiskState = {
  current_state: "NOMINAL",
  locked_out: false,
  drawdown_pct: 0.84,
  halt_dd_pct: 3.0,
  max_class_exposure_pct: 35,
  class_exposures_pct: { CRYPTO: 11.2, EQUITY: 21.4 },
  recent_transitions: [],
  compliance_alerts: [],
  emergency_events: [],
};

describe("riskAdapter", () => {
  it("maps what exists and marks var95/cvar/correlation as not computed", () => {
    const out = adaptRisk(risk, {
      warning_dd_pct: 1.5,
      caution_dd_pct: 2.5,
      halt_dd_pct: 3.0,
      max_class_exposure_pct: 35,
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out.spectrum.currentDrawdownPct).toBe(0.84);
    expect(out.spectrum.emergencyHaltPct).toBe(3.0);
    expect(out.spectrum.maxClassExposurePct).toBe(35);
    expect(out.spectrum.classExposurePct).toBeCloseTo(21.4, 5);
    expect(out.notComputed).toContain("var95IntradayPct");
    expect(out.notComputed).toContain("cvar99Pct");
    expect(out.notComputed).toContain("correlationExposure");
  });

  it("branches on {available:false}", () => {
    expect(adaptRisk({ available: false, reason: "r" } as unknown as RiskState)).toEqual({
      unavailable: "r",
    });
  });
});
