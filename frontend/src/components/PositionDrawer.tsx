import React from 'react';
import { Position } from '../types';
import { 
  X, 
  TrendingUp, 
  TrendingDown, 
  ShieldCheck, 
   
   
   
  AlertTriangle,

} from 'lucide-react';

interface PositionDrawerProps {
  position: Position | null;
  onClose: () => void;
  onTrimPosition?: (posId: string, pct: number) => void;
  onFlattenPosition?: (posId: string) => void;
}

export const PositionDrawer: React.FC<PositionDrawerProps> = ({
  position,
  onClose,
  onTrimPosition,
  onFlattenPosition,
}) => {
  if (!position) return null;

  const isProfitable = position.unrealizedPnlUsd >= 0;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-surface-deep backdrop-blur-sm flex justify-end animate-fade-in">
      <div className="w-full max-w-xl bg-[var(--color-surface-1)] border-l border-border-strong h-full shadow-2xl flex flex-col justify-between p-6 font-mono overflow-y-auto">
        {/* Drawer Header */}
        <div>
          <div className="flex items-center justify-between pb-4 border-b border-border-strong">
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded bg-accent shadow-[0_0_8px_var(--color-accent)]"></div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-text-strong tracking-tight">{position.symbol}</h2>
                  <span className={`text-xs px-2 py-0.5 rounded border font-semibold ${
                    position.side === 'LONG' 
                      ? 'bg-positive-bg text-positive border-positive' 
                      : 'bg-destructive-bg text-destructive border-destructive'
                  }`}>
                    {position.side}
                  </span>
                </div>
                <div className="text-xs text-text-muted mt-0.5">
                  ASSET CLASS: <strong className="text-text-strong">{position.assetClass}</strong>
                </div>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded bg-surface-veil hover:bg-surface-raised text-text-muted hover:text-text-strong transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Core Institutional Financials */}
          <div className="grid grid-cols-2 gap-3 my-4">
            <div className="p-3 rounded bg-surface-veil border border-border-subtle">
              <div className="text-[10px] text-text-muted">UNREALIZED P&L</div>
              <div className={`text-lg font-mono-num font-bold flex items-center gap-1 mt-1 ${isProfitable ? 'text-positive' : 'text-destructive'}`}>
                {isProfitable ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                {isProfitable ? '+' : ''}${position.unrealizedPnlUsd.toLocaleString()} ({isProfitable ? '+' : ''}{position.unrealizedPnlPct.toFixed(2)}%)
              </div>
            </div>

            <div className="p-3 rounded bg-surface-veil border border-border-subtle">
              <div className="text-[10px] text-text-muted">NOTIONAL VALUE</div>
              <div className="text-lg font-mono-num font-bold text-text-strong mt-1">
                ${position.notionalUsd.toLocaleString()}
              </div>
            </div>
          </div>

          {/* Pricing & Risk Parameters Grid */}
          <div className="p-3.5 rounded bg-surface-sunken border border-border-subtle space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-text-muted">CURRENT SIZE:</span>
              <span className="text-text-strong font-mono-num font-semibold">{position.size.toLocaleString()} units</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">ENTRY PRICE:</span>
              <span className="text-text-strong font-mono-num">${position.entryPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">CURRENT MARK:</span>
              <span className="text-accent font-mono-num font-semibold">${(position.markPrice || (position as any).currentPrice || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">PORTFOLIO WEIGHT:</span>
              <span className="text-text-strong font-mono-num">{(position.exposurePct || (position as any).portfolioWeightPct || 0).toFixed(2)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">RISK CONTRIBUTION:</span>
              <span className="text-warning font-mono-num">
                {position.varContributionUsd ? `$${(position.varContributionUsd / 1000).toFixed(0)}k VaR` : `${((position as any).riskContributionPct || 1.2).toFixed(2)}%`}
              </span>
            </div>
            {position.stopLossPrice && (
              <div className="flex justify-between border-t border-border-subtle pt-2">
                <span className="text-destructive flex items-center gap-1 font-semibold">
                  <AlertTriangle className="w-3 h-3 text-destructive" /> STOP-LOSS TRIGGER:
                </span>
                <span className="text-destructive font-mono font-bold">${position.stopLossPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              </div>
            )}
            {position.takeProfitPrice && (
              <div className="flex justify-between">
                <span className="text-positive font-semibold">TAKE PROFIT TARGET:</span>
                <span className="text-positive font-mono font-bold">${position.takeProfitPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              </div>
            )}
            {(position as any).liquidationPrice && (
              <div className="flex justify-between border-t border-border-subtle pt-2">
                <span className="text-destructive flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> ESTIMATED LIQUIDATION:
                </span>
                <span className="text-destructive font-mono-num">${(position as any).liquidationPrice.toLocaleString()}</span>
              </div>
            )}
          </div>

          {/* Strategy & Agent Lineage */}
          <div className="mt-4 p-3.5 rounded bg-surface-veil border border-border-subtle space-y-2 text-xs">
            <div className="text-[10px] text-text-muted uppercase tracking-wider">STRATEGY ALLOCATION &amp; MULTI-ASSET METADATA</div>
            <div className="flex justify-between">
              <span className="text-text-muted">STRATEGY:</span>
              <span className="text-text-strong font-semibold">{position.strategy ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">PROPOSING AGENT:</span>
              <span className="text-accent">{position.originatingAgent || (position as any).proposingAgent || '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">EXECUTION VENUE / CLOB:</span>
              <span className="text-text">{position.exchange || (position as any).venue || '—'}</span>
            </div>
            {position.country && (
              <div className="flex justify-between">
                <span className="text-text-muted">JURISDICTION / COUNTRY:</span>
                <span className="text-text-strong">{position.country} ({position.countryCode || 'INTL'})</span>
              </div>
            )}
            {position.polymarketOddsPct !== undefined && (
              <div className="flex justify-between border-t border-border-subtle pt-1.5 text-accent-magenta">
                <span>POLYMARKET CONSENSUS PROBABILITY:</span>
                <span className="font-bold">{position.polymarketOddsPct}% (Exp: {position.eventOutcomeDate})</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-text-muted">HOLDING DURATION:</span>
              <span className="text-text-subtle">— (not published)</span>
            </div>
          </div>

          {/* Constitutional Compliance Status */}
          <div className="mt-4 p-3 rounded bg-surface-veil border border-border-subtle text-xs flex items-center justify-between">
            <div className="flex items-center gap-2 text-text-muted">
              <ShieldCheck className="w-4 h-4" />
              <span>FIREWALL STATUS: NOT EVALUATED CLIENT-SIDE</span>
            </div>
            <span className="text-[10px] text-text-subtle font-mono">—</span>
          </div>
        </div>

        {/* Action Controls Footer */}
        <div className="mt-6 pt-4 border-t border-border-strong space-y-2">
          <div className="text-[10px] text-text-subtle uppercase tracking-wider mb-2">
            GOVERNANCE ACTIONS
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => onTrimPosition && onTrimPosition(position.id, 25)}
              className="py-2 px-3 rounded bg-surface-veil hover:bg-surface-raised border border-border-strong text-xs text-text-strong hover:text-text-strong transition-all font-semibold"
            >
              TRIM 25% NOTIONAL
            </button>
            <button
              onClick={() => onTrimPosition && onTrimPosition(position.id, 50)}
              className="py-2 px-3 rounded bg-surface-veil hover:bg-surface-raised border border-border-strong text-xs text-text-strong hover:text-text-strong transition-all font-semibold"
            >
              TRIM 50% NOTIONAL
            </button>
          </div>

          <button
            onClick={() => onFlattenPosition && onFlattenPosition(position.id)}
            className="w-full py-2.5 px-4 rounded bg-destructive hover:bg-destructive border border-destructive text-xs text-destructive hover:text-text-strong font-bold transition-all shadow-[0_0_12px_rgba(239,68,68,0.2)]"
          >
            FLATTEN POSITION (CLOSE 100%)
          </button>
        </div>
      </div>
    </div>
  );
};
