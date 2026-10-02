import React, { useState, useMemo } from 'react';
import { Position, AssetClass } from '../types';
import { 
  Globe, 
  TrendingUp, 
  TrendingDown, 
  Layers, 
   
   
   
   
  Grid3X3, 
   
   
  
  
  

} from 'lucide-react';

interface PortfolioConcentrationHeatmapProps {
  positions: Position[];
  onSelectPosition?: (position: Position) => void;
  className?: string;
}

type ColorMode = 'PNL' | 'NOTIONAL' | 'VAR_RISK' | 'EXPOSURE';
type ViewMode = 'HEATMAP' | 'GLOBAL_REGIONS' | 'CLASS_MATRIX';

export const PortfolioConcentrationHeatmap: React.FC<PortfolioConcentrationHeatmapProps> = ({
  positions,
  onSelectPosition,
  className = '',
}) => {
  const [selectedAssetClass, setSelectedAssetClass] = useState<string>('ALL');
  const [colorMode, setColorMode] = useState<ColorMode>('PNL');
  const [viewMode, setViewMode] = useState<ViewMode>('HEATMAP');
  const [, setHoveredPos] = useState<Position | null>(null);

  const totalNotional = useMemo(() => {
    return positions.reduce((sum, p) => sum + p.notionalUsd, 0) || 1;
  }, [positions]);

  const filteredPositions = useMemo(() => {
    if (selectedAssetClass === 'ALL') return positions;
    return positions.filter(p => p.assetClass === selectedAssetClass);
  }, [positions, selectedAssetClass]);

  // Group positions by asset class
  const classBreakdown = useMemo(() => {
    const map: Record<string, { count: number; notional: number; pnl: number; positions: Position[] }> = {};
    positions.forEach(p => {
      const cls = p.assetClass || 'OTHER';
      if (!map[cls]) {
        map[cls] = { count: 0, notional: 0, pnl: 0, positions: [] };
      }
      map[cls].count += 1;
      map[cls].notional += p.notionalUsd;
      map[cls].pnl += p.unrealizedPnlUsd;
      map[cls].positions.push(p);
    });
    return map;
  }, [positions]);

  // Group positions by geographic region / jurisdiction
  const regionBreakdown = useMemo(() => {
    const map: Record<string, { label: string; flag: string; notional: number; positions: Position[] }> = {
      'JP': { label: 'Japan / Asia-Pacific', flag: '🇯🇵', notional: 0, positions: [] },
      'EU': { label: 'Eurozone / Netherlands / Germany', flag: '🇪🇺', notional: 0, positions: [] },
      'US': { label: 'United States', flag: '🇺🇸', notional: 0, positions: [] },
      'GB': { label: 'United Kingdom / London LBMA', flag: '🇬🇧', notional: 0, positions: [] },
      'HK': { label: 'Hong Kong / China', flag: '🇭🇰', notional: 0, positions: [] },
      'IN': { label: 'India / Emerging Asia', flag: '🇮🇳', notional: 0, positions: [] },
      'BR': { label: 'Brazil / Latin America', flag: '🇧🇷', notional: 0, positions: [] },
      'PM': { label: 'Polymarket Global Prediction', flag: '🔮', notional: 0, positions: [] },
      'CRYPTO': { label: 'Decentralized Crypto Protocols', flag: '🌐', notional: 0, positions: [] },
      'XAU': { label: 'Sovereign Physical Bullion', flag: '🪙', notional: 0, positions: [] },
      'OIL': { label: 'North Sea / Global Energy', flag: '🛢️', notional: 0, positions: [] },
    };

    positions.forEach(p => {
      const code = p.countryCode || (p.assetClass === 'CRYPTO' ? 'CRYPTO' : p.assetClass === 'POLYMARKET' ? 'PM' : 'US');
      if (!map[code]) {
        map[code] = { label: p.country || 'International', flag: '🌍', notional: 0, positions: [] };
      }
      map[code].notional += p.notionalUsd;
      map[code].positions.push(p);
    });

    return Object.entries(map).filter(([_, data]) => data.positions.length > 0);
  }, [positions]);

  // Get color for tile depending on mode
  const getTileBg = (pos: Position) => {
    if (colorMode === 'PNL') {
      const pnl = pos.unrealizedPnlPct;
      if (pnl >= 8) return 'bg-positive-bg border-positive text-positive';
      if (pnl > 3) return 'bg-positive-bg border-positive text-positive';
      if (pnl > 0) return 'bg-accent-soft border-accent-soft text-accent-soft';
      if (pnl === 0) return 'bg-surface-deep border-border-strong text-text';
      if (pnl > -3) return 'bg-destructive-bg border-destructive text-destructive';
      return 'bg-destructive-bg border-destructive text-destructive';
    }

    if (colorMode === 'NOTIONAL') {
      const share = (pos.notionalUsd / totalNotional) * 100;
      if (share >= 15) return 'bg-info-bg border-accent text-accent';
      if (share >= 8) return 'bg-info-bg border-accent text-accent';
      if (share >= 4) return 'bg-accent-info border-accent-info text-accent-info';
      return 'bg-surface-deep border-border-subtle text-text';
    }

    if (colorMode === 'VAR_RISK') {
      const varContrib = pos.varContributionUsd || 50000;
      if (varContrib > 200000) return 'bg-warning-bg border-warning text-warning';
      if (varContrib > 100000) return 'bg-warning-bg border-warning text-warning';
      return 'bg-surface-deep border-border-subtle text-text';
    }

    // EXPOSURE
    const exp = pos.exposurePct || 5;
    if (exp >= 12) return 'bg-violet border-violet text-violet';
    if (exp >= 6) return 'bg-violet border-violet text-violet';
    return 'bg-surface-deep border-border-subtle text-text';
  };

  const getAssetClassBadge = (assetClass: AssetClass | string) => {
    switch (assetClass) {
      case 'POLYMARKET':
        return { label: 'POLYMARKET', bg: 'bg-accent-magenta text-accent-magenta border-accent-magenta' };
      case 'GLOBAL_EQUITY':
        return { label: 'GLOBAL EQUITY', bg: 'bg-info-bg text-accent border-accent' };
      case 'COMMODITY':
        return { label: 'COMMODITY', bg: 'bg-warning-bg text-warning border-warning' };
      case 'FX':
        return { label: 'FOREX / FX', bg: 'bg-positive-bg text-positive border-positive' };
      case 'US_EQUITY':
        return { label: 'US EQUITY', bg: 'bg-info-bg text-accent-info border-accent-info' };
      case 'CRYPTO':
        return { label: 'CRYPTO', bg: 'bg-violet text-violet border-violet' };
      case 'RATES':
        return { label: 'SOVEREIGN RATES', bg: 'bg-surface-2 text-text border-border-subtle' };
      default:
        return { label: assetClass, bg: 'bg-surface-2 text-text border-border-subtle' };
    }
  };

  return (
    <div className={`bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl font-mono space-y-4 ${className}`}>
      {/* Visualizer Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-accent" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-text-strong">
            MULTI-ASSET PORTFOLIO CONCENTRATION &amp; GLOBAL REGIME MAP
          </h3>
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent font-semibold">
            GLOBAL ARBITRAGE &amp; MACRO
          </span>
        </div>

        {/* View Mode Switcher */}
        <div className="flex items-center gap-1 bg-surface-deep p-0.5 rounded border border-border-strong text-[10px]">
          <button
            onClick={() => setViewMode('HEATMAP')}
            className={`px-2.5 py-1 rounded flex items-center gap-1 transition-all ${
              viewMode === 'HEATMAP'
                ? 'bg-info-bg text-accent font-bold border border-accent shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                : 'text-text-muted hover:text-text-strong'
            }`}
          >
            <Grid3X3 className="w-3 h-3" />
            <span>TREEMAP HEATMAP</span>
          </button>
          <button
            onClick={() => setViewMode('GLOBAL_REGIONS')}
            className={`px-2.5 py-1 rounded flex items-center gap-1 transition-all ${
              viewMode === 'GLOBAL_REGIONS'
                ? 'bg-info-bg text-accent font-bold border border-accent shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                : 'text-text-muted hover:text-text-strong'
            }`}
          >
            <Globe className="w-3 h-3" />
            <span>GLOBAL JURISDICTIONS</span>
          </button>
          <button
            onClick={() => setViewMode('CLASS_MATRIX')}
            className={`px-2.5 py-1 rounded flex items-center gap-1 transition-all ${
              viewMode === 'CLASS_MATRIX'
                ? 'bg-info-bg text-accent font-bold border border-accent shadow-[0_0_8px_rgba(0,240,255,0.2)]'
                : 'text-text-muted hover:text-text-strong'
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>CLASS MATRIX</span>
          </button>
        </div>
      </div>

      {/* Control Strip: Asset Class Filters & Color Coding */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        {/* Asset Class Filter Pills */}
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-[10px] text-text-subtle mr-1 uppercase">Filter:</span>
          {['ALL', 'POLYMARKET', 'GLOBAL_EQUITY', 'COMMODITY', 'FX', 'US_EQUITY', 'CRYPTO', 'RATES'].map(cls => (
            <button
              key={cls}
              onClick={() => setSelectedAssetClass(cls)}
              className={`px-2 py-0.5 rounded text-[10px] transition-all border ${
                selectedAssetClass === cls
                  ? 'bg-accent text-text-strong font-bold border-accent shadow-[0_0_8px_rgba(0,240,255,0.4)]'
                  : 'bg-surface-veil border-border-subtle text-text-muted hover:text-text-strong'
              }`}
            >
              {cls.replace('_', ' ')}
            </button>
          ))}
        </div>

        {/* Color Metric Selector */}
        <div className="flex items-center gap-2 text-[10px]">
          <span className="text-text-subtle uppercase">Color By:</span>
          <div className="flex items-center gap-1 bg-surface-sunken p-0.5 rounded border border-border-subtle">
            {(['PNL', 'NOTIONAL', 'VAR_RISK', 'EXPOSURE'] as ColorMode[]).map(mode => (
              <button
                key={mode}
                onClick={() => setColorMode(mode)}
                className={`px-2 py-0.5 rounded ${
                  colorMode === mode
                    ? 'bg-surface-raised text-text-strong font-bold'
                    : 'text-text-muted hover:text-text-strong'
                }`}
              >
                {mode.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* VIEW 1: PROPORTIONAL CONCENTRATION TREEMAP HEATMAP */}
      {viewMode === 'HEATMAP' && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {filteredPositions.map((pos) => {
              const notionalShare = ((pos.notionalUsd / totalNotional) * 100);
              const badge = getAssetClassBadge(pos.assetClass);
              const isPnlPos = pos.unrealizedPnlUsd >= 0;

              return (
                <div
                  key={pos.id}
                  onClick={() => onSelectPosition && onSelectPosition(pos)}
                  onMouseEnter={() => setHoveredPos(pos)}
                  onMouseLeave={() => setHoveredPos(null)}
                  className={`p-3 rounded border transition-all cursor-pointer group flex flex-col justify-between relative overflow-hidden shadow-sm hover:shadow-[0_0_15px_rgba(0,240,255,0.15)] ${getTileBg(pos)}`}
                  style={{
                    minHeight: '140px'
                  }}
                >
                  {/* Top: Symbol, Asset Class Badge, and Country/Exchange */}
                  <div>
                    <div className="flex items-start justify-between gap-1">
                      <div>
                        <div className="flex items-center gap-1.5 font-bold text-sm text-text-strong group-hover:text-accent transition-colors">
                          <span>{pos.symbol}</span>
                          {pos.countryCode && (
                            <span className="text-[10px] text-text-muted px-1 rounded bg-surface-sunken border border-border-strong">
                              {pos.countryCode}
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-text truncate max-w-[170px]" title={pos.name}>
                          {pos.name}
                        </div>
                      </div>

                      <span className={`text-[8px] px-1.5 py-0.5 rounded border uppercase font-bold tracking-tight whitespace-nowrap ${badge.bg}`}>
                        {badge.label}
                      </span>
                    </div>

                    {/* Specific multi-asset callouts */}
                    {pos.assetClass === 'POLYMARKET' && pos.polymarketOddsPct !== undefined && (
                      <div className="mt-1.5 p-1 rounded bg-surface-deep border border-accent-magenta flex items-center justify-between text-[9px]">
                        <span className="text-accent-magenta font-bold">Odds: {pos.polymarketOddsPct}%</span>
                        <span className="text-text-muted">Res: {pos.eventOutcomeDate || '2026'}</span>
                      </div>
                    )}

                    {pos.assetClass === 'GLOBAL_EQUITY' && pos.localCurrency && (
                      <div className="mt-1.5 p-1 rounded bg-surface-deep border border-accent flex items-center justify-between text-[9px]">
                        <span className="text-accent font-semibold">{pos.exchange || 'International'}</span>
                        <span className="text-text font-mono">Cur: {pos.localCurrency}</span>
                      </div>
                    )}

                    {pos.assetClass === 'COMMODITY' && (
                      <div className="mt-1.5 p-1 rounded bg-surface-deep border border-warning flex items-center justify-between text-[9px]">
                        <span className="text-warning font-semibold">{pos.exchange || 'CME/ICE'}</span>
                        <span className="text-text">Roll: Active</span>
                      </div>
                    )}

                    {pos.assetClass === 'FX' && (
                      <div className="mt-1.5 p-1 rounded bg-surface-deep border border-positive flex items-center justify-between text-[9px]">
                        <span className="text-positive font-semibold">G10/EM Carry</span>
                        <span className="text-text">Side: {pos.side}</span>
                      </div>
                    )}
                  </div>

                  {/* Bottom: Notional, P&L, Weight */}
                  <div className="mt-2 pt-2 border-t border-border-subtle flex items-end justify-between">
                    <div>
                      <div className="text-[9px] text-text-muted">NOTIONAL</div>
                      <div className="text-xs font-bold font-mono text-text-strong">
                        ${(pos.notionalUsd / 1000000).toFixed(2)}M
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-[9px] text-text-muted">P&amp;L ({notionalShare.toFixed(1)}% w)</div>
                      <div className={`text-xs font-bold font-mono flex items-center justify-end gap-0.5 ${
                        isPnlPos ? 'text-positive' : 'text-destructive'
                      }`}>
                        {isPnlPos ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        {isPnlPos ? '+' : ''}{pos.unrealizedPnlPct.toFixed(1)}%
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* VIEW 2: GLOBAL JURISDICTIONS & REGIONAL FLOW */}
      {viewMode === 'GLOBAL_REGIONS' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {regionBreakdown.map(([code, region]) => {
              const share = ((region.notional / totalNotional) * 100);
              return (
                <div key={code} className="bg-surface-sunken border border-border-strong rounded p-3 space-y-2.5">
                  <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-base">{region.flag}</span>
                      <div>
                        <div className="text-xs font-bold text-text-strong">{region.label}</div>
                        <div className="text-[10px] text-text-muted">{region.positions.length} Positions Active</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-bold font-mono text-accent">
                        ${(region.notional / 1000000).toFixed(2)}M
                      </div>
                      <div className="text-[10px] text-text-muted font-mono">{share.toFixed(1)}% of fund</div>
                    </div>
                  </div>

                  {/* Mini bar */}
                  <div className="w-full bg-surface-raised h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-accent h-full rounded-full transition-all"
                      style={{ width: `${Math.min(share * 2.5, 100)}%` }}
                    />
                  </div>

                  {/* List of symbols in this region */}
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {region.positions.map(p => (
                      <span
                        key={p.id}
                        onClick={() => onSelectPosition && onSelectPosition(p)}
                        className="text-[10px] px-2 py-0.5 rounded bg-surface-veil hover:bg-info-bg hover:text-accent border border-border-subtle cursor-pointer transition-colors"
                      >
                        {p.symbol} ({p.unrealizedPnlPct >= 0 ? '+' : ''}{p.unrealizedPnlPct.toFixed(1)}%)
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* VIEW 3: ASSET CLASS MATRIX */}
      {viewMode === 'CLASS_MATRIX' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {(Object.entries(classBreakdown) as [string, { count: number; notional: number; pnl: number; positions: Position[] }][]).map(([cls, data]) => {
              const share = ((data.notional / totalNotional) * 100);
              const badge = getAssetClassBadge(cls);
              const isPositive = data.pnl >= 0;

              return (
                <div key={cls} className="bg-surface-sunken border border-border-strong rounded p-3.5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className={`text-[9px] px-2 py-0.5 rounded border uppercase font-bold ${badge.bg}`}>
                      {badge.label}
                    </span>
                    <span className="text-xs font-mono font-bold text-text-strong">
                      {share.toFixed(1)}%
                    </span>
                  </div>

                  <div>
                    <div className="text-[10px] text-text-muted">Total Notional</div>
                    <div className="text-sm font-bold font-mono text-text-strong">
                      ${(data.notional / 1000000).toFixed(2)}M
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-xs pt-2 border-t border-border-subtle">
                    <span className="text-text-muted">Unrealized P&amp;L:</span>
                    <span className={`font-mono font-bold ${isPositive ? 'text-positive' : 'text-destructive'}`}>
                      {isPositive ? '+' : ''}${(data.pnl / 1000).toFixed(1)}k
                    </span>
                  </div>

                  <div className="text-[10px] text-text-muted">
                    Constituents: <span className="text-text-strong">{data.positions.map(p => p.symbol).join(', ')}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Bottom Summary Bar */}
      <div className="pt-3 border-t border-border-subtle flex flex-wrap items-center justify-between gap-3 text-[10px] text-text-muted">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-accent-magenta"></span>
            <span>Polymarket Prediction CLOB</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-accent"></span>
            <span>Global Equities (Japan/EU/Asia/LatAm)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-warning"></span>
            <span>Commodities (Gold/Brent/Copper)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-positive"></span>
            <span>Forex &amp; EM Carry</span>
          </div>
        </div>

        <div className="font-mono text-text">
          Constitutional Concentration Cap: <span className="text-accent font-bold">25.0% Single / 35.0% Class</span> (100% Compliant)
        </div>
      </div>
    </div>
  );
};
