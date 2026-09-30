/**
 * V2 shared primitives: icons, formatting, tone badges, panels, stat tiles,
 * DataTable, SVG line/bar charts, honest empty states. Zero dependencies.
 */
import type { ReactNode } from "react";
import { useMemo } from "react";

/* ------------------------------------------------------------------ icons */

const P = {
  gauge: "M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z",
  wallet: "M21 7.3V6a2 2 0 00-2-2H4a2 2 0 00-2 2v12a2 2 0 002 2h15a2 2 0 002-2v-1.3a2 2 0 001-1.7V9a2 2 0 00-1-1.7zM19 18H4V6h15v2h-6a2 2 0 00-2 2v4a2 2 0 002 2h6v2zm1-5h-6v-3h6v3z",
  layers: "M11.99 18.54l-7.37-5.73L3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z",
  swap: "M6.99 11L3 15l3.99 4v-3H14v-2H6.99v-3zM21 9l-3.99-4v3H10v2h7.01v3L21 9z",
  shield: "M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.9h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v7.71z",
  ops: "M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65a.5.5 0 00.12-.64l-2-3.46a.5.5 0 00-.61-.22l-2.49 1a7.3 7.3 0 00-1.69-.98l-.38-2.65A.49.49 0 0014 2h-4a.49.49 0 00-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1a.5.5 0 00-.61.22l-2 3.46a.5.5 0 00.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65a.5.5 0 00-.12.64l2 3.46c.14.24.42.34.61.22l2.49-1c.52.39 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65a7.3 7.3 0 001.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46a.5.5 0 00-.12-.64l-2.11-1.65zM12 15.5a3.5 3.5 0 110-7 3.5 3.5 0 010 7z",
  agents: "M12 2a7 7 0 00-7 7c0 2.38 1.19 4.47 3 5.74V17a1 1 0 001 1h6a1 1 0 001-1v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 00-7-7zM9 21a1 1 0 001 1h4a1 1 0 001-1v-1H9v1z",
  globe: "M12 2a10 10 0 100 20 10 10 0 000-20zm7.93 9h-3.98a15.6 15.6 0 00-1.38-6.03A8.02 8.02 0 0119.93 11zM12 4.06c.83 1.2 1.83 3.46 1.94 6.94h-3.89c.11-3.48 1.11-5.74 1.95-6.94zM4.07 13h3.98c.15 2.3.65 4.35 1.38 6.03A8.02 8.02 0 014.07 13zm3.98-2H4.07a8.02 8.02 0 015.36-6.03A15.6 15.6 0 008.05 11zM12 19.94c-.84-1.2-1.84-3.46-1.95-6.94h3.89c-.1 3.48-1.1 5.74-1.94 6.94zm2.57-.91A15.6 15.6 0 0015.95 13h3.98a8.02 8.02 0 01-5.36 6.03z",
  bell: "M12 22a2 2 0 002-2h-4a2 2 0 002 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4a1.5 1.5 0 00-3 0v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z",
  flask: "M13 11.33L18 18H6l5-6.67V5h2v6.33zM9 3a1 1 0 00-1 1v6.67L2.8 18.4A1 1 0 003.6 20h16.8a1 1 0 00.8-1.6L16 10.67V4a1 1 0 00-1-1H9z",
  chip: "M15 9H9v6h6V9zm-2 4h-2v-2h2v2zm8-2V9h-2V7a2 2 0 00-2-2h-2V3h-2v2h-2V3H9v2H7a2 2 0 00-2 2v2H3v2h2v2H3v2h2v2a2 2 0 002 2h2v2h2v-2h2v2h2v-2h2a2 2 0 002-2v-2h2v-2h-2v-2h2zm-4 6H7V7h10v10z",
  book: "M18 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V4a2 2 0 00-2-2zM6 4h5v8l-2.5-1.5L6 12V4z",
  scale: "M12 3a2 2 0 012 2v1h5a1 1 0 011 1v3h-2V8h-4.22a5.5 5.5 0 01-2.56 2.71A6 6 0 0113 13v6h4v2H7v-2h4v-6a6 6 0 01-2.22-.29A5.5 5.5 0 016.22 8H4v2H2V7a1 1 0 011-1h7V5a2 2 0 012-2z",
  audit: "M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm4 18H6V4h7v5h5v11zM8 12h8v2H8v-2zm0 4h8v2H8v-2z",
  pulse: "M22 12h-4l-3 9L9 3l-3 9H2v2h5.5l1.5-4.5L13 19l2.5-7H22v-2z",
  gear: "M19.14 12.98c.04-.32.07-.64.07-.98s-.02-.66-.07-.98l2.12-1.65a.5.5 0 00.12-.64l-2-3.46a.5.5 0 00-.61-.22l-2.49 1a7.3 7.3 0 00-1.69-.98l-.38-2.65A.49.49 0 0014 2h-4a.49.49 0 00-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1a.5.5 0 00-.61.22l-2 3.46a.5.5 0 00.12.64l2.11 1.65c-.04.32-.07.65-.07.98l-2.11 1.65a.5.5 0 00-.12.64l2 3.46c.14.24.42.34.61.22l2.49-1c.52.39 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65a7.3 7.3 0 001.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46a.5.5 0 00-.12-.64l-2.11-1.65zM12 15.5a3.5 3.5 0 110-7 3.5 3.5 0 010 7z",
  term: "M20 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V6a2 2 0 00-2-2zM7.7 15.3l-1.4-1.4L8.6 11 6.3 8.7l1.4-1.4L11.4 11l-3.7 4.3z",
  cmd: "M18 3v3h-3V3h3zM9 3v3H6V3h3zm12 6v3h-3V9h3zM6 9v3H3V9h3zm12 6v3h-3v-3h3zm-9 0v3H6v-3h3z",
  target: "M12 2a10 10 0 100 20 10 10 0 000-20zm0 18a8 8 0 110-16 8 8 0 010 16zm0-13a5 5 0 100 10 5 5 0 000-10zm0 8a3 3 0 110-6 3 3 0 010 6z",
  chart: "M3.5 18.5l6-6 4 4L21 8.5 19.6 7l-6.1 6.1-4-4L2 17l1.5 1.5z",
};

export type IconName = keyof typeof P;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d={P[name]} />
    </svg>
  );
}

/* -------------------------------------------------------------- formatting */

export const fmt = {
  money(v: number | null | undefined, digits = 0): string {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const sign = v < 0 ? "-" : "";
    return `${sign}$${Math.abs(v).toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })}`;
  },
  num(v: number | null | undefined, digits = 2): string {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return v.toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  },
  pct(v: number | null | undefined, digits = 1): string {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return `${v.toFixed(digits)}%`;
  },
  signedPct(v: number | null | undefined, digits = 2): string {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
  },
  moneySigned(v: number | null | undefined, digits = 0): string {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return `${v >= 0 ? "+" : "−"}$${Math.abs(v).toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })}`;
  },
  ts(iso: string | null | undefined): string {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString("en-US", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  },
  short(iso: string | null | undefined): string {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString("en-US", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  },
  ago(iso: string | null | undefined): string {
    if (!iso) return "—";
    const ms = Date.now() - new Date(iso).getTime();
    if (Number.isNaN(ms)) return "—";
    const s = Math.max(0, Math.floor(ms / 1000));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  },
  qty(v: number | null | undefined): string {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  },
};

/** Tone classifier for the handful of statuses that recur across the API. */
export function toneFor(s: string | null | undefined): string {
  const v = (s ?? "").toUpperCase();
  if (["OK", "PASS", "FILLED", "APPROVED", "SUPPORTED", "ACTIVE", "LIVE", "CONNECTED", "NORMAL", "HEALTHY", "COMPLETE", "MATCHED"].includes(v)) return "ok";
  if (["REJECTED", "FAIL", "FAILED", "DENIED", "LOCKOUT", "EMERGENCY_HALT", "REJECTED_HYPOTHESIS", "DEAD_LETTER", "BLOCKED", "BROKEN"].includes(v)) return "bad";
  if (["PENDING", "WARN", "WARNING", "INCONCLUSIVE", "STALE", "PARTIAL", "DEGRADED", "SUPERVISED", "REQUIRES_APPROVAL", "HALT"].includes(v)) return "warn";
  if (["PAPER", "SHADOW", "UNTESTED", "TESTING", "INFO"].includes(v)) return "info";
  return "dim";
}

export const pnlTone = (v: number | null | undefined): string =>
  v === null || v === undefined ? "dim" : v > 0 ? "pos" : v < 0 ? "neg" : "dim";

/* ------------------------------------------------------------------ layout */

export function PageHead({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="page-title">
      <h1>{title}</h1>
      {sub && <span className="sub">{sub}</span>}
      <span style={{ flex: 1 }} />
      {right}
    </div>
  );
}

export function Panel({
  title,
  right,
  children,
  scroll,
  tall,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
  scroll?: boolean;
  tall?: boolean;
}) {
  return (
    <section className="panel">
      <div className="panel-h">
        <span>{title}</span>
        {right && <span className="right">{right}</span>}
      </div>
      <div className={`panel-b${scroll ? " tight" : ""}`}>
        {scroll ? <div className={`scroll${tall ? " tall" : ""}`}>{children}</div> : children}
      </div>
    </section>
  );
}

export function Stat({
  k,
  v,
  s,
  tone,
}: {
  k: string;
  v: string;
  s?: string;
  tone?: "pos" | "neg" | "warn" | "info";
}) {
  return (
    <div className="stat">
      <div className="k">{k}</div>
      <div className={`v${tone ? ` ${tone}` : ""}`}>{v}</div>
      {s && <div className="s">{s}</div>}
    </div>
  );
}

export function Badge({ children, tone = "dim", fill }: { children: ReactNode; tone?: string; fill?: boolean }) {
  return <span className={`badge tone-${tone}${fill ? " fill" : ""}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

/** Honest "this surface is not wired in this process" state (kernel contract). */
export function UnavailableBox({ reason }: { reason: string }) {
  return (
    <div className="empty">
      <div style={{ marginBottom: 4 }}>⚠️ not available: {reason}</div>
      <div style={{ fontSize: 11 }}>The backend reported this surface as unavailable rather than empty — nothing is invented here.</div>
    </div>
  );
}

/* --------------------------------------------------------------- DataTable */

export interface Col<T> {
  key: string;
  head: string;
  num?: boolean;
  w?: string;
  render: (row: T) => ReactNode;
}

export function DataTable<T>({
  cols,
  rows,
  onRow,
  selected,
  empty = "Nothing here yet.",
  max,
}: {
  cols: Col<T>[];
  rows: T[] | null | undefined;
  onRow?: (row: T) => void;
  selected?: (row: T) => boolean;
  empty?: string;
  max?: number;
}) {
  if (!rows || rows.length === 0) return <Empty>{empty}</Empty>;
  const shown = max ? rows.slice(0, max) : rows;
  return (
    <table className="t">
      <thead>
        <tr>
          {cols.map((c) => (
            <th key={c.key} className={c.num ? "num" : ""} style={c.w ? { width: c.w } : undefined}>
              {c.head}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {shown.map((r, i) => (
          <tr
            key={i}
            onClick={onRow ? () => onRow(r) : undefined}
            className={`${onRow ? "click" : ""} ${selected?.(r) ? "sel" : ""}`}
            style={onRow ? { cursor: "pointer" } : undefined}
          >
            {cols.map((c) => (
              <td key={c.key} className={c.num ? "num" : ""}>
                {c.render(r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ----------------------------------------------------------------- charts */

export function LineChart({
  series,
  height = 240,
  yFmt = (v: number) => fmt.money(v),
}: {
  series: { name: string; color: string; data: number[] }[];
  height?: number;
  yFmt?: (v: number) => string;
}) {
  const W = 1000;
  const PADL = 8;
  const PADR = 62;
  const H = height;
  const all = series.flatMap((s) => s.data).filter((v) => Number.isFinite(v));
  const { path, area, zeroY, min, max, lastPts } = useMemo(() => {
    if (all.length < 2) {
      return { path: "", area: "", zeroY: null as number | null, min: 0, max: 0, lastPts: [] as { y: number; color: string }[] };
    }
    const mn = Math.min(...all, 0);
    const mx = Math.max(...all, 0);
    const span = mx - mn || 1;
    const x = (i: number, n: number) => PADL + (i / Math.max(1, n - 1)) * (W - PADL - PADR);
    const y = (v: number) => 10 + (1 - (v - mn) / span) * (H - 20);
    const paths = series.map((s) => {
      if (s.data.length < 2) return "";
      return s.data.map((v, i) => `${i === 0 ? "M" : "L"}${x(i, s.data.length).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    });
    const areaPath = paths[0]
      ? `${paths[0]} L${x(series[0].data.length - 1, series[0].data.length).toFixed(1)},${y(Math.max(mn, 0)).toFixed(1)} L${PADL},${y(Math.max(mn, 0)).toFixed(1)} Z`
      : "";
    const last = series.map((s) => ({ y: y(s.data[s.data.length - 1] ?? 0), color: s.color }));
    return { path: paths, area: areaPath, zeroY: mn < 0 && mx > 0 ? y(0) : null, min: mn, max: mx, lastPts: last };
  }, [series, all.length, H]);

  if (!path) return <Empty>Not enough data to chart.</Empty>;
  const paths = Array.isArray(path) ? path : [path];

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height }}>
        {area && <path d={area} fill="url(#lcgrad)" opacity="0.5" />}
        <defs>
          <linearGradient id="lcgrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={series[0]?.color ?? "#4cc2ff"} stopOpacity="0.18" />
            <stop offset="100%" stopColor={series[0]?.color ?? "#4cc2ff"} stopOpacity="0" />
          </linearGradient>
        </defs>
        {zeroY !== null && (
          <line x1={PADL} x2={W - PADR} y1={zeroY} y2={zeroY} stroke="var(--line)" strokeDasharray="3 4" />
        )}
        {paths.map((d, i) => (
          <path key={i} d={d} fill="none" stroke={series[i]?.color} strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
        ))}
        {lastPts.map((pt, i) => (
          <g key={`l${i}`}>
            <line x1={W - PADR} x2={W} y1={pt.y} y2={pt.y} stroke={pt.color} strokeDasharray="2 3" opacity="0.6" vectorEffect="non-scaling-stroke" />
            <text x={W - PADR + 6} y={pt.y + 3.5} fill={pt.color} fontSize="11" fontFamily="var(--mono)">
              {yFmt(series[i]?.data[series[i].data.length - 1] ?? 0)}
            </text>
          </g>
        ))}
        <text x={PADL} y={12} fill="var(--faint)" fontSize="10" fontFamily="var(--mono)">{yFmt(max)}</text>
        <text x={PADL} y={H - 2} fill="var(--faint)" fontSize="10" fontFamily="var(--mono)">{yFmt(min)}</text>
      </svg>
    </div>
  );
}

export function BarChart({
  data,
  height = 150,
  posColor = "var(--ok)",
  negColor = "var(--bad)",
  yFmt = (v: number) => fmt.money(v),
}: {
  data: { label: string; value: number }[];
  height?: number;
  posColor?: string;
  negColor?: string;
  yFmt?: (v: number) => string;
}) {
  if (!data.length) return <Empty>No data.</Empty>;
  const W = 1000;
  const H = height;
  const maxAbs = Math.max(...data.map((d) => Math.abs(d.value)), 1e-9);
  const zeroY = H / 2;
  const bw = (W - 60) / data.length;
  const allNeg = data.every((d) => d.value <= 0);
  const allPos = data.every((d) => d.value >= 0);
  const base = allNeg ? 12 : allPos ? H - 24 : zeroY;
  const scale = (H - 36) / 2 / maxAbs;
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height }}>
        <line x1={0} x2={W} y1={base} y2={base} stroke="var(--line)" />
        {data.map((d, i) => {
          const h = Math.abs(d.value) * (allNeg || allPos ? (H - 36) / maxAbs : scale);
          const y = d.value >= 0 ? base - h : base;
          return (
            <g key={i}>
              <rect
                x={30 + i * bw + bw * 0.15}
                y={y}
                width={Math.max(1, bw * 0.7)}
                height={Math.max(1, h)}
                fill={d.value >= 0 ? posColor : negColor}
                opacity="0.8"
                rx="1"
              />
              {(data.length <= 14 || i % Math.ceil(data.length / 14) === 0) && (
                <text x={30 + i * bw + bw / 2} y={H - 4} fill="var(--faint)" fontSize="9.5" textAnchor="middle" fontFamily="var(--mono)">
                  {d.label}
                </text>
              )}
            </g>
          );
        })}
        <text x={2} y={12} fill="var(--faint)" fontSize="9.5" fontFamily="var(--mono)">{yFmt(maxAbs)}</text>
        <text x={2} y={H - 14} fill="var(--faint)" fontSize="9.5" fontFamily="var(--mono)">{yFmt(-maxAbs)}</text>
      </svg>
    </div>
  );
}

/** Tiny distribution bar (e.g. hypothesis status counts). */
export function DistBar({ parts, height = 8 }: { parts: { label: string; value: number; color: string }[]; height?: number }) {
  const total = parts.reduce((a, b) => a + b.value, 0);
  if (!total) return <Empty>No data.</Empty>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", height, borderRadius: 4, overflow: "hidden", background: "var(--panel-2)" }}>
        {parts.map((p) => (
          <div key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.label}: ${p.value}`} />
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px" }}>
        {parts.map((p) => (
          <span key={p.label} className="ind" style={{ color: p.color }}>
            <span className="dot" style={{ background: p.color }} /> {p.label} {p.value}
          </span>
        ))}
      </div>
    </div>
  );
}
