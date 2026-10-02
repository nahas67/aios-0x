import React, { useState, useRef, useMemo } from 'react';
import { 
  TrajectoryDataPoint, 
  TimelineEvent, 
  TimelineEventType 
} from '../types';
import { 
  TrendingUp, 
  ShieldCheck, 
  Zap, 
  Users, 
   
  Sparkles, 
  UserCheck, 
   
  Info,

} from 'lucide-react';

interface CapitalTrajectoryChartProps {
  data: TrajectoryDataPoint[];
  onSelectEvent?: (event: TimelineEvent) => void;
  className?: string;
}

export const CapitalTrajectoryChart: React.FC<CapitalTrajectoryChartProps> = ({
  data,
  onSelectEvent,
  className = '',
}) => {
  const [timeframe, setTimeframe] = useState<'1D' | '1W' | '1M' | 'YTD' | 'ALL'>('1D');
  const [activeLayers, setActiveLayers] = useState({
    nav: true,
    benchmark: true,
    drawdown: true,
    events: true,
    utilization: false,
  });
  const [hoveredPoint, setHoveredPoint] = useState<TrajectoryDataPoint | null>(null);
  const [hoveredEvent, setHoveredEvent] = useState<TimelineEvent | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Bounds calculation
  const navValues = useMemo(() => data.map(d => d.nav), [data]);
  const minNav = useMemo(() => Math.min(...navValues) * 0.998, [navValues]);
  const maxNav = useMemo(() => Math.max(...navValues) * 1.002, [navValues]);
  const navRange = maxNav - minNav || 1;

  // ViewBox dimensions
  const width = 1000;
  const height = 360;
  const padding = { top: 30, right: 50, bottom: 40, left: 70 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Coordinate scales
  const getX = (index: number) => padding.left + (index / (data.length - 1)) * chartWidth;
  const getY = (nav: number) => padding.top + chartHeight - ((nav - minNav) / navRange) * chartHeight;

  // Benchmark scale (normalized to start with NAV)
  const firstNav = data[0]?.nav ?? 0;
  const firstBm = data[0]?.benchmark ?? 0;
  const getBenchmarkY = (bm: number) => {
    const scaledNav = firstBm !== 0 ? firstNav * (bm / firstBm) : firstNav;
    return getY(scaledNav);
  };

  // SVG paths
  const navPoints = data.map((d, i) => `${getX(i)},${getY(d.nav)}`);
  const navPath = `M ${navPoints.join(' L ')}`;
  const navAreaPath = `${navPath} L ${getX(data.length - 1)},${padding.top + chartHeight} L ${getX(0)},${padding.top + chartHeight} Z`;

  const bmPoints = data.map((d, i) => `${getX(i)},${getBenchmarkY(d.benchmark)}`);
  const bmPath = `M ${bmPoints.join(' L ')}`;

  const currentNav = data[data.length - 1]?.nav ?? 0;
  const currentPnl = data[data.length - 1]?.intradayPnl ?? 0;
  const pnlDenom = currentNav - currentPnl;
  const pnlPct = pnlDenom !== 0 ? ((currentPnl / pnlDenom) * 100).toFixed(2) : "0.00";
  const currentDd = data[data.length - 1]?.drawdownPct ?? 0;
  const currentUtil = data[data.length - 1]?.capitalUtilizationPct ?? 0;

  const getEventIcon = (type: TimelineEventType) => {
    switch (type) {
      case 'AGENT_CONSENSUS':
        return <Users className="w-3 h-3 text-accent" />;
      case 'RISK_REDUCTION':
        return <ShieldCheck className="w-3 h-3 text-warning" />;
      case 'POSITION_OPENED':
        return <Zap className="w-3 h-3 text-positive" />;
      case 'REGIME_SHIFT':
        return <Sparkles className="w-3 h-3 text-violet" />;
      case 'MODEL_PROMOTED':
        return <TrendingUp className="w-3 h-3 text-accent-info" />;
      case 'HUMAN_APPROVAL':
        return <UserCheck className="w-3 h-3 text-accent-soft" />;
      default:
        return <Info className="w-3 h-3 text-text-muted" />;
    }
  };

  const getEventColor = (type: TimelineEventType) => {
    switch (type) {
      case 'AGENT_CONSENSUS': return 'border-accent bg-info-bg text-accent shadow-[0_0_8px_rgba(0,240,255,0.4)]';
      case 'RISK_REDUCTION': return 'border-warning bg-warning-bg text-warning shadow-[0_0_8px_rgba(245,158,11,0.4)]';
      case 'POSITION_OPENED': return 'border-positive bg-positive-bg text-positive shadow-[0_0_8px_rgba(16,185,129,0.4)]';
      case 'REGIME_SHIFT': return 'border-violet bg-violet text-violet shadow-[0_0_8px_rgba(129,140,248,0.4)]';
      case 'MODEL_PROMOTED': return 'border-accent-info bg-accent-info text-accent-info shadow-[0_0_8px_rgba(59,130,246,0.4)]';
      case 'HUMAN_APPROVAL': return 'border-accent-soft bg-accent-soft text-accent-soft shadow-[0_0_8px_rgba(45,212,191,0.4)]';
      default: return 'border-border-subtle bg-surface-deep text-text';
    }
  };

  return (
    <div className={`relative bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 flex flex-col justify-between overflow-hidden shadow-2xl ${className}`}>
      {/* Background Subtle Gradient Grid */}
      <div className="absolute inset-0 bg-grid-subtle opacity-40 pointer-events-none" />
      <div className="absolute top-0 right-0 w-96 h-96 bg-accent rounded-full blur-3xl pointer-events-none" />

      {/* Header & Metrics Strip */}
      <div className="relative z-10 flex flex-wrap items-start justify-between gap-4 pb-3 border-b border-border-subtle">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase font-mono tracking-widest text-text-muted">
              PORTFOLIO TRAJECTORY ENGINE
            </span>
            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-info-bg text-accent border border-accent">
              DETERMINISTIC NET ASSET VALUE
            </span>
          </div>

          <div className="flex items-baseline gap-3 mt-1">
            <span className="text-2xl lg:text-3xl font-mono-num font-bold tracking-tight text-text-strong">
              ${(currentNav / 1000000).toFixed(2)}M
            </span>
            <span className="text-sm font-mono-num font-medium text-positive flex items-center gap-1">
              <TrendingUp className="w-3.5 h-3.5" />
              +${(currentPnl / 1000).toFixed(1)}k ({pnlPct}%)
            </span>
            <span className="text-xs font-mono text-text-muted">
              INTRADAY
            </span>
          </div>
        </div>

        {/* Institutional Statistics Pill Strip */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="bg-surface-veil border border-border-subtle px-2.5 py-1 rounded">
            <div className="text-[10px] font-mono text-text-muted">MAX DRAWDOWN</div>
            <div className="text-xs font-mono-num font-semibold text-text-strong">{currentDd.toFixed(2)}%</div>
          </div>
          <div className="bg-surface-veil border border-border-subtle px-2.5 py-1 rounded">
            <div className="text-[10px] font-mono text-text-muted">CAPITAL UTILIZATION</div>
            <div className="text-xs font-mono-num font-semibold text-accent">{currentUtil.toFixed(1)}%</div>
          </div>
          <div className="bg-surface-veil border border-border-subtle px-2.5 py-1 rounded">
            <div className="text-[10px] font-mono text-text-muted">SHARPE RATIO</div>
            <div className="text-xs font-mono-num font-semibold text-positive">2.84</div>
          </div>
          <div className="bg-surface-veil border border-border-subtle px-2.5 py-1 rounded">
            <div className="text-[10px] font-mono text-text-muted">BETA TO SPX</div>
            <div className="text-xs font-mono-num font-semibold text-text-strong">0.42</div>
          </div>

          {/* Timeframe selector */}
          <div className="flex items-center bg-surface-sunken p-0.5 rounded border border-border-subtle">
            {(['1D', '1W', '1M', 'YTD', 'ALL'] as const).map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-0.5 text-[11px] font-mono rounded transition-colors ${
                  timeframe === tf
                    ? 'bg-info-bg text-accent border border-accent font-semibold'
                    : 'text-text-muted hover:text-text-strong'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Layer Toggles */}
      <div className="relative z-10 flex items-center justify-between py-2 text-[11px] font-mono text-text-muted">
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1.5 cursor-pointer hover:text-text-strong select-none">
            <input
              type="checkbox"
              checked={activeLayers.nav}
              onChange={() => setActiveLayers(l => ({ ...l, nav: !l.nav }))}
              className="accent-accent w-3 h-3 rounded"
            />
            <span className="w-2.5 h-0.5 bg-accent inline-block"></span>
            <span>CAPITAL TRAJECTORY (NAV)</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer hover:text-text-strong select-none">
            <input
              type="checkbox"
              checked={activeLayers.benchmark}
              onChange={() => setActiveLayers(l => ({ ...l, benchmark: !l.benchmark }))}
              className="accent-violet w-3 h-3 rounded"
            />
            <span className="w-2.5 h-0.5 border-t border-dashed border-violet inline-block"></span>
            <span>HEDGE FUND COMPOSITE BENCHMARK</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer hover:text-text-strong select-none">
            <input
              type="checkbox"
              checked={activeLayers.events}
              onChange={() => setActiveLayers(l => ({ ...l, events: !l.events }))}
              className="accent-positive w-3 h-3 rounded"
            />
            <span className="w-1.5 h-1.5 rounded-full bg-accent inline-block"></span>
            <span>CONSENSUS & DECISION EVENTS</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer hover:text-text-strong select-none">
            <input
              type="checkbox"
              checked={activeLayers.drawdown}
              onChange={() => setActiveLayers(l => ({ ...l, drawdown: !l.drawdown }))}
              className="accent-warning w-3 h-3 rounded"
            />
            <span className="w-2 h-2 rounded-sm bg-warning border border-warning inline-block"></span>
            <span>DRAWDOWN SUB-SURFACE</span>
          </label>
        </div>

        <div className="text-[10px] text-text-subtle font-mono hidden sm:block">
          SCALE: 1:1 REAL-TIME HYPERTABLE
        </div>
      </div>

      {/* SVG Canvas Area */}
      <div 
        ref={containerRef}
        className="relative z-10 w-full flex-1 min-h-[260px] cursor-crosshair select-none"
        onMouseMove={(e) => {
          if (!containerRef.current) return;
          const rect = containerRef.current.getBoundingClientRect();
          const mouseX = e.clientX - rect.left;
          const relativeX = (mouseX / rect.width) * width;
          setMousePos({ x: mouseX, y: e.clientY - rect.top });

          // Find closest data point
          const chartMouseX = relativeX - padding.left;
          const index = Math.round((chartMouseX / chartWidth) * (data.length - 1));
          if (index >= 0 && index < data.length) {
            setHoveredPoint(data[index]);
          }
        }}
        onMouseLeave={() => {
          setHoveredPoint(null);
          setHoveredEvent(null);
          setMousePos(null);
        }}
      >
        <svg 
          viewBox={`0 0 ${width} ${height}`} 
          className="w-full h-full overflow-visible"
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id="navAreaGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.18" />
              <stop offset="60%" stopColor="var(--color-accent)" stopOpacity="0.04" />
              <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="navLineGradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" style={{stopColor: 'var(--color-accent-info)'}} />
              <stop offset="60%" style={{stopColor: 'var(--color-accent)'}} />
              <stop offset="100%" style={{stopColor: 'var(--color-accent-soft)'}} />
            </linearGradient>
          </defs>

          {/* Grid lines (horizontal) */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
            const y = padding.top + chartHeight * ratio;
            const value = maxNav - ratio * navRange;
            return (
              <g key={i}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={width - padding.right}
                  y2={y}
                  stroke="rgba(255, 255, 255, 0.05)"
                  strokeDasharray="3 3"
                />
                <text
                  x={padding.left - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="text-[10px] font-mono fill-text-subtle select-none"
                >
                  ${(value / 1000000).toFixed(1)}M
                </text>
              </g>
            );
          })}

          {/* Time axis labels (vertical) */}
          {data.map((d, i) => {
            if (i % 2 !== 0 && i !== data.length - 1) return null;
            const x = getX(i);
            return (
              <g key={i}>
                <line
                  x1={x}
                  y1={padding.top}
                  x2={x}
                  y2={padding.top + chartHeight}
                  stroke="rgba(255, 255, 255, 0.03)"
                />
                <text
                  x={x}
                  y={height - 12}
                  textAnchor="middle"
                  className="text-[10px] font-mono fill-text-muted select-none"
                >
                  {d.time}
                </text>
              </g>
            );
          })}

          {/* Drawdown Area (bottom sub-layer if active) */}
          {activeLayers.drawdown && (
            <g opacity="0.35">
              {data.map((d, i) => {
                if (i === 0) return null;
                const prevX = getX(i - 1);
                const currX = getX(i);
                const ddHeight = d.drawdownPct * 30; // scaled
                const baseY = padding.top + chartHeight;
                return (
                  <rect
                    key={`dd-${i}`}
                    x={prevX}
                    y={baseY - ddHeight}
                    width={currX - prevX}
                    height={ddHeight}
                    fill="rgba(245, 158, 11, 0.4)"
                  />
                );
              })}
            </g>
          )}

          {/* Benchmark line */}
          {activeLayers.benchmark && (
            <path
              d={bmPath}
              fill="none"
              stroke="var(--color-violet)"
              strokeWidth="1.5"
              strokeDasharray="4 3"
              opacity="0.8"
            />
          )}

          {/* NAV Area Gradient */}
          {activeLayers.nav && (
            <path
              d={navAreaPath}
              fill="url(#navAreaGradient)"
            />
          )}

          {/* NAV Primary Line */}
          {activeLayers.nav && (
            <path
              d={navPath}
              fill="none"
              stroke="url(#navLineGradient)"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Timeline Event Markers */}
          {activeLayers.events && data.map((d, i) => {
            if (!d.event) return null;
            const cx = getX(i);
            const cy = getY(d.nav);
            const isHovered = hoveredEvent?.id === d.event.id;

            return (
              <g 
                key={d.event.id}
                className="cursor-pointer transition-transform duration-150"
                onClick={() => onSelectEvent && onSelectEvent(d.event!)}
                onMouseEnter={() => setHoveredEvent(d.event!)}
                onMouseLeave={() => setHoveredEvent(null)}
              >
                {/* Ping animation ring */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={isHovered ? 12 : 7}
                  fill="none"
                  stroke="var(--color-accent)"
                  strokeWidth="1"
                  className="animate-ping opacity-30"
                />

                {/* Vertical drop line to axis */}
                <line
                  x1={cx}
                  y1={cy}
                  x2={cx}
                  y2={padding.top + chartHeight}
                  stroke="rgba(0, 240, 255, 0.3)"
                  strokeDasharray="2 2"
                />

                {/* Outer badge dot */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={isHovered ? 7 : 5}
                  fill="var(--color-surface-rail)"
                  stroke="var(--color-accent)"
                  strokeWidth="2"
                />

                {/* Inner core */}
                <circle
                  cx={cx}
                  cy={cy}
                  r="2.5"
                  style={{fill: 'var(--color-text-strong)'}}
                />
              </g>
            );
          })}

          {/* Hover Crosshair line */}
          {hoveredPoint && (
            <g>
              {(() => {
                const index = data.findIndex(d => d.time === hoveredPoint.time);
                if (index < 0) return null;
                const hx = getX(index);
                const hy = getY(hoveredPoint.nav);

                return (
                  <>
                    <line
                      x1={hx}
                      y1={padding.top}
                      x2={hx}
                      y2={padding.top + chartHeight}
                      stroke="rgba(255, 255, 255, 0.3)"
                      strokeWidth="1"
                      strokeDasharray="3 3"
                    />
                    <circle
                      cx={hx}
                      cy={hy}
                      r="4"
                      fill="var(--color-accent)"
                      stroke="var(--color-text-strong)"
                      strokeWidth="1.5"
                      className="shadow-lg"
                    />
                  </>
                );
              })()}
            </g>
          )}
        </svg>

        {/* Floating Precision Tooltip */}
        {hoveredPoint && mousePos && (
          <div 
            className="absolute pointer-events-none z-30 bg-[var(--color-surface-1)]//95 border border-accent rounded shadow-2xl p-2.5 text-xs font-mono backdrop-blur-md min-w-[200px]"
            style={{
              left: Math.min(mousePos.x + 15, (containerRef.current?.clientWidth || 600) - 220),
              top: Math.max(10, mousePos.y - 80),
            }}
          >
            <div className="flex items-center justify-between pb-1 border-b border-border-strong text-[10px] text-text-muted">
              <span>TIMESTAMP: {hoveredPoint.time} UTC</span>
              <span className="text-accent">TICK #184k</span>
            </div>

            <div className="py-1.5 space-y-1">
              <div className="flex justify-between items-baseline">
                <span className="text-text-muted">PORTFOLIO NAV:</span>
                <span className="font-mono-num font-bold text-text-strong text-sm">
                  ${(hoveredPoint.nav / 1000000).toFixed(3)}M
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">INTRADAY P&L:</span>
                <span className="font-mono-num text-positive font-semibold">
                  +${(hoveredPoint.intradayPnl / 1000).toFixed(1)}k
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">DRAWDOWN:</span>
                <span className="font-mono-num text-warning">
                  {hoveredPoint.drawdownPct.toFixed(2)}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">UTILIZATION:</span>
                <span className="font-mono-num text-text-strong">
                  {hoveredPoint.capitalUtilizationPct.toFixed(1)}%
                </span>
              </div>
            </div>

            {hoveredPoint.event && (
              <div className="mt-1.5 pt-1.5 border-t border-accent text-[11px] text-accent flex items-center gap-1.5">
                {getEventIcon(hoveredPoint.event.type)}
                <span className="font-semibold">{hoveredPoint.event.title}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Timeline Event Pill Bar */}
      <div className="relative z-10 mt-3 pt-2.5 border-t border-border-subtle flex items-center gap-2 overflow-x-auto pb-1">
        <span className="text-[10px] font-mono text-text-subtle uppercase tracking-widest shrink-0">
          EVENT TRACE:
        </span>
        {data.filter(d => d.event).map(d => {
          const evt = d.event!;
          return (
            <button
              key={evt.id}
              onClick={() => onSelectEvent && onSelectEvent(evt)}
              className={`flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-mono border transition-all shrink-0 hover:scale-[1.02] ${getEventColor(evt.type)}`}
            >
              {getEventIcon(evt.type)}
              <span className="font-semibold tracking-tight">{evt.time}:</span>
              <span className="text-text max-w-[140px] truncate">{evt.title}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
