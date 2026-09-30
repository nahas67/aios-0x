/**
 * Zero-dependency responsive SVG charts. Handle zero data, partial data,
 * negative values, loading, and resize. No fake data is ever synthesized
 * here — empty arrays render as explicit empty states.
 */
import { useLayoutEffect, useRef, useState } from "react";
import { fmtNum, fmtPrice } from "../lib/format";
import { Empty } from "./ui";

function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setW(e.contentRect.width);
    });
    ro.observe(el);
    setW(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

export interface Series {
  values: number[];
  color: string;
  label: string;
  dashed?: boolean;
}

export function LineChart({
  series,
  height = 200,
  formatValue = fmtPrice,
  zeroLine = false,
}: {
  series: Series[];
  height?: number;
  formatValue?: (n: number) => string;
  zeroLine?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ x: number; i: number } | null>(null);
  const padL = 54;
  const padR = 10;
  const padT = 8;
  const padB = 18;
  const plotW = Math.max(0, width - padL - padR);
  const plotH = height - padT - padB;

  const all = series.flatMap((s) => s.values);
  const n = Math.max(...series.map((s) => s.values.length), 0);
  if (!all.length || n < 2 || width === 0) {
    return (
      <div ref={ref} style={{ width: "100%" }}>
        <div style={{ height }}>
          <Empty>No time-series data yet — the curve appears as the engine records outcomes.</Empty>
        </div>
      </div>
    );
  }

  let min = Math.min(...all);
  let max = Math.max(...all);
  if (zeroLine) {
    min = Math.min(min, 0);
    max = Math.max(max, 0);
  }
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const x = (i: number) => padL + (i / (n - 1)) * plotW;
  const y = (v: number) => padT + (1 - (v - min) / (max - min)) * plotH;

  const gridVals = [0, 0.25, 0.5, 0.75, 1].map((f) => min + f * (max - min));
  const hoverI = hover ? Math.max(0, Math.min(n - 1, Math.round(((hover.x - padL) / plotW) * (n - 1)))) : null;

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label="Time series chart"
        onMouseMove={(e) => {
          const rect = (e.target as SVGElement).ownerSVGElement?.getBoundingClientRect();
          if (rect) setHover({ x: e.clientX - rect.left, i: 0 });
        }}
        onMouseLeave={() => setHover(null)}
      >
        {gridVals.map((v, gi) => (
          <g key={gi}>
            <line x1={padL} x2={width - padR} y1={y(v)} y2={y(v)} stroke="#151b21" strokeWidth={1} />
            <text x={padL - 6} y={y(v) + 3} textAnchor="end" fontSize={9} fill="#455a64" fontFamily="var(--font-mono)">
              {formatValue(v)}
            </text>
          </g>
        ))}
        {zeroLine && min < 0 && max > 0 && (
          <line x1={padL} x2={width - padR} y1={y(0)} y2={y(0)} stroke="#2a343e" strokeWidth={1} strokeDasharray="3 3" />
        )}
        {series.map((s, si) => {
          const pts = s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
          return (
            <polyline
              key={si}
              points={pts}
              fill="none"
              stroke={s.color}
              strokeWidth={1.6}
              strokeDasharray={s.dashed ? "4 3" : undefined}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          );
        })}
        {hoverI !== null && (
          <g>
            <line x1={x(hoverI)} x2={x(hoverI)} y1={padT} y2={height - padB} stroke="#2e3944" strokeWidth={1} />
            {series.map((s, si) =>
              s.values[hoverI] !== undefined ? (
                <circle key={si} cx={x(hoverI)} cy={y(s.values[hoverI])} r={2.6} fill={s.color} />
              ) : null,
            )}
            {series.map((s, si) =>
              s.values[hoverI] !== undefined ? (
                <text
                  key={`l${si}`}
                  x={Math.min(x(hoverI) + 6, width - 90)}
                  y={padT + 12 + si * 12}
                  fontSize={9}
                  fill={s.color}
                  fontFamily="var(--font-mono)"
                >
                  {s.label}: {formatValue(s.values[hoverI])}
                </text>
              ) : null,
            )}
          </g>
        )}
      </svg>
    </div>
  );
}

export function Sparkline({
  values,
  color = "#00e5ff",
  height = 30,
}: {
  values: number[];
  color?: string;
  height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  if (values.length < 2 || width === 0) {
    return (
      <div ref={ref} style={{ width: "100%", height }}>
        <Empty>
          <span style={{ fontSize: 11 }}>not enough data</span>
        </Empty>
      </div>
    );
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => `${(i / (values.length - 1)) * width},${height - 3 - ((v - min) / span) * (height - 6)}`)
    .join(" ");
  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width={width} height={height} aria-hidden="true">
        <polyline points={pts} fill="none" stroke={color} strokeWidth={1.4} />
      </svg>
    </div>
  );
}

export function BarChart({
  entries,
  height = 170,
  formatValue = fmtNum,
}: {
  entries: { label: string; value: number }[];
  height?: number;
  formatValue?: (n: number) => string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  if (!entries.length || width === 0) {
    return (
      <div ref={ref} style={{ width: "100%" }}>
        <Empty>No data yet</Empty>
      </div>
    );
  }
  const padL = 8;
  const padB = 26;
  const maxAbs = Math.max(...entries.map((e) => Math.abs(e.value)), 1e-9);
  const zeroLine = entries.some((e) => e.value < 0);
  const plotH = height - padB - 14;
  const zeroY = zeroLine ? 14 + plotH / 2 : 14 + plotH;
  const slot = (width - padL * 2) / entries.length;
  const barW = Math.min(46, slot * 0.62);
  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width={width} height={height} role="img" aria-label="Bar chart">
        <line x1={padL} x2={width - padL} y1={zeroY} y2={zeroY} stroke="#232b33" strokeWidth={1} />
        {entries.map((e, i) => {
          const h = (Math.abs(e.value) / maxAbs) * (zeroLine ? plotH / 2 : plotH);
          const cx = padL + i * slot + slot / 2;
          const top = e.value >= 0 ? zeroY - h : zeroY;
          const color = e.value >= 0 ? "#00e676" : "#ff1744";
          return (
            <g key={e.label}>
              <rect x={cx - barW / 2} y={top} width={barW} height={Math.max(1.5, h)} fill={color} rx={2.5} opacity={0.85} />
              <text x={cx} y={height - 14} textAnchor="middle" fontSize={9} fill="#90a4ae">
                {e.label.length > 12 ? `${e.label.slice(0, 11)}…` : e.label}
              </text>
              <text x={cx} y={e.value >= 0 ? top - 3 : top + h + 10} textAnchor="middle" fontSize={9} fill={color} fontFamily="var(--font-mono)">
                {formatValue(e.value)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function Donut({
  entries,
  size = 150,
}: {
  entries: { label: string; value: number }[];
  size?: number;
}) {
  const palette = ["#00e5ff", "#00e676", "#ffc400", "#ff1744", "#7c8fa6", "#b388ff", "#ff9e80", "#80d8ff"];
  const total = entries.reduce((a, e) => a + Math.max(0, e.value), 0);
  if (total <= 0) return <Empty>No allocation data</Empty>;
  const r = size / 2 - 12;
  const c = size / 2;
  const circ = 2 * Math.PI * r;
  let offset = 0;
  const segs = entries
    .filter((e) => e.value > 0)
    .map((e, i) => {
      const frac = e.value / total;
      const seg = { ...e, frac, dash: frac * circ, offset, color: palette[i % palette.length] };
      offset += seg.dash;
      return seg;
    });
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
      <svg width={size} height={size} role="img" aria-label="Allocation donut chart">
        <g transform={`rotate(-90 ${c} ${c})`}>
          {segs.map((s) => (
            <circle
              key={s.label}
              cx={c}
              cy={c}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={14}
              strokeDasharray={`${Math.max(0, s.dash - 1.5)} ${circ}`}
              strokeDashoffset={-s.offset}
            />
          ))}
        </g>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {segs.map((s) => (
          <span key={s.label} style={{ fontSize: 12, color: "var(--text-dim)" }}>
            <span className="dot" style={{ background: s.color }} />
            {s.label} — {(s.frac * 100).toFixed(1)}%
          </span>
        ))}
      </div>
    </div>
  );
}

export function Gauge({
  label,
  valuePct,
  warnAt = 70,
  badAt = 90,
  display,
}: {
  label: string;
  valuePct: number | null;
  warnAt?: number;
  badAt?: number;
  display?: string;
}) {
  const v = valuePct === null ? null : Math.max(0, Math.min(100, valuePct));
  const tone = v === null ? "dim" : v >= badAt ? "bad" : v >= warnAt ? "warn" : "ok";
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
        <span className="dim">{label}</span>
        <span className={`pill ${tone === "dim" ? "dim" : tone}`}>{display ?? (v === null ? "—" : `${v.toFixed(1)}%`)}</span>
      </div>
      <div className="progress">
        <i style={{ width: `${v ?? 0}%`, background: tone === "bad" ? "var(--bad)" : tone === "warn" ? "var(--warn)" : "var(--cyan)" }} />
      </div>
    </div>
  );
}
