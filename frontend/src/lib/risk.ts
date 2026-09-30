/** Risk-state semantics shared by banner, pills, and gauges. */

export type Tone = "ok" | "warn" | "bad" | "info" | "dim";

export function riskTone(state: string | null | undefined): Tone {
  const s = (state || "").toUpperCase();
  if (s === "NORMAL") return "ok";
  if (s === "GUARDED") return "warn";
  if (s === "CAUTION") return "warn";
  if (s === "WARNING") return "warn";
  if (s === "EMERGENCY_HALT" || s === "LOCKOUT") return "bad";
  return "dim";
}

export function autonomyTone(mode: string | null | undefined): Tone {
  switch ((mode || "").toUpperCase()) {
    case "AUTONOMOUS":
      return "warn";
    case "SUPERVISED":
      return "info";
    case "ASSISTED":
      return "info";
    case "MANUAL":
      return "dim";
    default:
      return "dim";
  }
}

export function severityTone(sev: string | null | undefined): Tone {
  switch ((sev || "").toUpperCase()) {
    case "CRITICAL":
      return "bad";
    case "WARNING":
      return "warn";
    case "IMPORTANT":
      return "warn";
    case "INFO":
      return "info";
    default:
      return "dim";
  }
}
