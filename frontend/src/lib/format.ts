/** Locale-aware formatting. No hardcoded number formats. */

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});
const usdCompact = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 2,
});
const usd4 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 4,
});
const num = new Intl.NumberFormat("en-US");
const pct1 = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const pct2 = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function fmtUsd(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : usd.format(v);
}
export function fmtUsdCompact(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : usdCompact.format(v);
}
export function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v < 10 ? usd4.format(v) : usd.format(v);
}
export function fmtNum(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : num.format(v);
}
export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return (digits === 1 ? pct1 : pct2).format(v / 100);
}
export function fmtSigned(v: number | null | undefined, fmt: (n: number) => string): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return (v >= 0 ? "+" : "") + fmt(v);
}
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString([], { hour12: false });
}
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString([], { hour12: false, month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
export function agoLabel(tsMs: number | null | undefined): string {
  if (tsMs === null || tsMs === undefined) return "never";
  const s = Math.max(0, Math.round((Date.now() - tsMs) / 1000));
  if (s < 5) return "now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}
export function pnlClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  return v > 0 ? "pos" : v < 0 ? "neg" : "";
}
export function statusTone(status: string): "ok" | "warn" | "bad" | "info" | "dim" {
  const s = status.toUpperCase();
  if (["FILLED", "OK", "PASS", "APPROVED", "NOMINAL", "NORMAL", "READY", "LIVE", "HEALTHY"].includes(s)) return "ok";
  if (["PENDING", "PARTIAL", "PENDING_APPROVAL", "GUARDED", "CAUTION", "WARNING", "INCONCLUSIVE", "EVALUATED", "DEGRADED", "STALE"].includes(s)) return "warn";
  if (["REJECTED", "FAIL", "EMERGENCY_HALT", "LOCKOUT", "CRITICAL", "CANCELLED", "ERROR", "BROKEN"].includes(s)) return "bad";
  if (["QUEUED", "OPEN", "SUBMITTED", "TRIAL", "EVALUATING"].includes(s)) return "info";
  return "dim";
}
