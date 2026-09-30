/**
 * riskAdapter: /api/v1/risk (+ optional /api/v1/settings risk slice)
 * → zip RiskSpectrum.
 *
 * The backend does not compute var95 / cvar99 / portfolio correlation, so
 * those fields are 0 with a "not computed" note — the views render "—"
 * instead of inventing a number.
 */
import type { RiskState } from "../api/types";
import type { RiskSpectrum } from "../types";
import { type Unavailable } from "./absent";

export interface SettingsRiskSlice {
  warning_dd_pct: number | null;
  caution_dd_pct: number | null;
  halt_dd_pct: number | null;
  max_class_exposure_pct: number | null;
}

export interface AdaptedRisk {
  spectrum: RiskSpectrum;
  /** Spectrum fields the backend does not compute. Views render these as "—". */
  notComputed: string[];
}

export const RISK_NOT_COMPUTED = [
  "var95IntradayPct",
  "cvar99Pct",
  "correlationExposure",
  "positionConcentrationPct",
] as const;

export function adaptRisk(
  risk: RiskState | { available: false; reason?: string },
  settings: SettingsRiskSlice | null = null,
): AdaptedRisk | Unavailable {
  if ("available" in risk) {
    const reason = risk.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "risk state unavailable" };
  }
  const notComputed: string[] = [...RISK_NOT_COMPUTED];
  const emergencyHaltPct = risk.halt_dd_pct ?? settings?.halt_dd_pct ?? 0;
  if (risk.halt_dd_pct == null && settings?.halt_dd_pct == null) {
    notComputed.push("emergencyHaltPct");
  }
  const warningThresholdPct = settings?.warning_dd_pct ?? settings?.caution_dd_pct ?? 0;
  if (warningThresholdPct === 0) notComputed.push("warningThresholdPct");
  const reductionThresholdPct = settings?.caution_dd_pct ?? settings?.warning_dd_pct ?? 0;
  if (reductionThresholdPct === 0) notComputed.push("reductionThresholdPct");

  const exposures = Object.values(risk.class_exposures_pct ?? {});
  const classExposurePct = exposures.length > 0 ? Math.max(...exposures) : 0;
  if (risk.drawdown_pct == null) notComputed.push("currentDrawdownPct");

  return {
    spectrum: {
      currentDrawdownPct: risk.drawdown_pct ?? 0,
      warningThresholdPct,
      reductionThresholdPct,
      emergencyHaltPct,
      positionConcentrationPct: 0,
      maxPositionConcentrationPct: 0,
      classExposurePct,
      maxClassExposurePct: risk.max_class_exposure_pct ?? settings?.max_class_exposure_pct ?? 0,
      correlationExposure: 0,
      maxCorrelationExposure: 0,
      var95IntradayPct: 0,
      cvar99Pct: 0,
      leverage: "not computed",
      marginStatus: "not computed",
    },
    notComputed,
  };
}
