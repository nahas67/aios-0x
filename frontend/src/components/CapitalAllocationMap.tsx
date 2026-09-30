import React, { useState } from 'react';
import { AllocationSegment } from '../types';
import { Layers } from 'lucide-react';

interface CapitalAllocationMapProps {
  segments: AllocationSegment[];
  onSelectSegment?: (segment: AllocationSegment) => void;
  className?: string;
}

export const CapitalAllocationMap: React.FC<CapitalAllocationMapProps> = ({
  segments,
  onSelectSegment,
  className = '',
}) => {
  const [selectedId, setSelectedId] = useState<string>(segments[0]?.id || '');
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const activeSegment = segments.find(s => s.id === (hoveredId || selectedId)) || segments[0];

  // SVG Concentric Radial Coordinates Calculation
  const size = 260;
  const center = size / 2;

  // Compute ring arcs
  let currentAngle = -90; // Start at top
  const arcs = segments.map((seg) => {
    const angleSpan = (seg.currentExposurePct / 100) * 360;
    const startAngle = currentAngle;
    const endAngle = currentAngle + angleSpan;
    currentAngle = endAngle;

    // SVG arc calculation helper
    const polarToCartesian = (centerX: number, centerY: number, radius: number, angleInDegrees: number) => {
      const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180.0;
      return {
        x: centerX + radius * Math.cos(angleInRadians),
        y: centerY + radius * Math.sin(angleInRadians),
      };
    };

    const createArc = (radius: number, start: number, end: number) => {
      // Offset by 90 to match start at top
      const p1 = polarToCartesian(center, center, radius, end + 90);
      const p2 = polarToCartesian(center, center, radius, start + 90);
      const largeArcFlag = end - start <= 180 ? '0' : '1';
      return `M ${p1.x} ${p1.y} A ${radius} ${radius} 0 ${largeArcFlag} 0 ${p2.x} ${p2.y}`;
    };

    return {
      seg,
      startAngle,
      endAngle,
      currentArcPath: createArc(88, startAngle, endAngle - 1.5),
      targetArcPath: createArc(106, startAngle, startAngle + (seg.targetExposurePct / 100) * 360 - 1.5),
    };
  });

  return (
    <div className={`bg-[#0d0f17] border border-white/[0.08] rounded-md p-3.5 shadow-2xl flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-mono font-bold tracking-wider text-slate-100 uppercase">
            CAPITAL ALLOCATION ENGINE
          </h3>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-white/[0.04] text-slate-400 border border-white/[0.06]">
            FRACTIONAL KELLY OPTIMIZED
          </span>
        </div>

        <div className="text-[11px] font-mono text-slate-400">
          TOTAL EXPOSURE: <span className="text-cyan-300 font-bold">{segments.reduce((acc, s) => acc + s.currentExposurePct, 0).toFixed(1)}%</span>
        </div>
      </div>

      {/* Main Content Area: Radial Canvas + Detailed Layered Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 py-2 items-center">
        {/* Left: Concentric Radial Allocation Map */}
        <div className="lg:col-span-5 flex flex-col items-center justify-center relative">
          <div className="relative w-[260px] h-[260px]">
            <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-full transform">
              {/* Outer guide ring */}
              <circle
                cx={center}
                cy={center}
                r="116"
                fill="none"
                stroke="rgba(255, 255, 255, 0.04)"
                strokeDasharray="2 4"
              />
              <circle
                cx={center}
                cy={center}
                r="72"
                fill="none"
                stroke="rgba(255, 255, 255, 0.04)"
              />

              {/* Target Exposure Rings (Outer, thinner) */}
              {arcs.map(({ seg, targetArcPath }) => {
                const isSelected = activeSegment?.id === seg.id;
                return (
                  <path
                    key={`target-${seg.id}`}
                    d={targetArcPath}
                    fill="none"
                    stroke={seg.color}
                    strokeWidth="3"
                    strokeOpacity={isSelected ? 0.9 : 0.3}
                    strokeDasharray="2 2"
                  />
                );
              })}

              {/* Current Exposure Primary Arcs (Inner, thick) */}
              {arcs.map(({ seg, currentArcPath }) => {
                const isSelected = activeSegment?.id === seg.id;
                return (
                  <path
                    key={`curr-${seg.id}`}
                    d={currentArcPath}
                    fill="none"
                    stroke={seg.color}
                    strokeWidth={isSelected ? 14 : 10}
                    className="cursor-pointer transition-all duration-200"
                    strokeLinecap="round"
                    onMouseEnter={() => setHoveredId(seg.id)}
                    onMouseLeave={() => setHoveredId(null)}
                    onClick={() => {
                      setSelectedId(seg.id);
                      if (onSelectSegment) onSelectSegment(seg);
                    }}
                    style={{
                      filter: isSelected ? `drop-shadow(0 0 8px ${seg.color})` : 'none',
                    }}
                  />
                );
              })}
            </svg>

            {/* Concentric Center Info */}
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none p-6">
              <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">
                ALLOCATED
              </span>
              <span className="text-xl font-mono-num font-bold text-white tracking-tight">
                {activeSegment ? activeSegment.currentExposurePct.toFixed(1) : '100'}%
              </span>
              <span className="text-[10px] font-mono text-slate-400 max-w-[120px] truncate mt-0.5">
                {activeSegment ? activeSegment.name.split(' ')[0] : 'Total Portfolio'}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3 text-[10px] font-mono text-slate-500 mt-1">
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-1 bg-cyan-400 inline-block rounded"></span> CURRENT
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-0.5 border-t border-dashed border-cyan-400 inline-block"></span> TARGET
            </span>
          </div>
        </div>

        {/* Right: Detailed Layered Institutional Metric Breakdown */}
        <div className="lg:col-span-7 space-y-2">
          {segments.map((seg) => {
            const isSelected = activeSegment?.id === seg.id;
            return (
              <div
                key={seg.id}
                onClick={() => {
                  setSelectedId(seg.id);
                  if (onSelectSegment) onSelectSegment(seg);
                }}
                onMouseEnter={() => setHoveredId(seg.id)}
                onMouseLeave={() => setHoveredId(null)}
                className={`p-2 rounded border transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-white/[0.05] border-cyan-500/40 shadow-[0_0_12px_rgba(0,240,255,0.08)]'
                    : 'bg-white/[0.02] border-white/[0.05] hover:bg-white/[0.03]'
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span 
                      className="w-2 h-2 rounded-full shrink-0" 
                      style={{ backgroundColor: seg.color }}
                    />
                    <span className="font-medium text-slate-200">{seg.name}</span>
                  </div>

                  <div className="flex items-center gap-3 font-mono text-[11px]">
                    <span className="text-slate-400">
                      ${(seg.notionalUsd / 1000000).toFixed(1)}M
                    </span>
                    <span className="font-mono-num font-bold text-white">
                      {seg.currentExposurePct.toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Progress bar comparing Current vs Target */}
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="flex-1 h-1.5 bg-black/40 rounded-full overflow-hidden relative">
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{
                        width: `${seg.currentExposurePct}%`,
                        backgroundColor: seg.color,
                      }}
                    />
                    {/* Target indicator line */}
                    <div
                      className="absolute top-0 bottom-0 w-0.5 bg-white shadow-sm"
                      style={{ left: `${seg.targetExposurePct}%` }}
                      title={`Target: ${seg.targetExposurePct}%`}
                    />
                  </div>

                  <span className="text-[10px] font-mono text-slate-400 shrink-0">
                    tgt {seg.targetExposurePct.toFixed(0)}%
                  </span>
                </div>

                {/* Micro Institutional Risk Factor Grid */}
                <div className="mt-2 grid grid-cols-3 gap-2 text-[10px] font-mono pt-1.5 border-t border-white/[0.04]">
                  <div>
                    <span className="text-slate-500">RISK CONTRIB:</span>{' '}
                    <span className="text-slate-300 font-medium font-mono-num">{seg.riskContributionPct.toFixed(1)}%</span>
                  </div>
                  <div>
                    <span className="text-slate-500">CORRELATION:</span>{' '}
                    <span className="text-slate-300 font-medium font-mono-num">{seg.correlation.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">DD CONTRIB:</span>{' '}
                    <span className="text-amber-400 font-medium font-mono-num">{seg.drawdownContributionPct.toFixed(2)}%</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
