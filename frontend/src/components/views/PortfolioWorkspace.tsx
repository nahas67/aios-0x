import React, { useState } from 'react';
import { Position } from '../../types';
import {
  PieChart,
  TrendingUp,
  Search,
  Plus,
  X
} from 'lucide-react';
import { CapitalAllocationMap } from '../CapitalAllocationMap';
import { PortfolioConcentrationHeatmap } from '../PortfolioConcentrationHeatmap';
import { portfolioApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { useStreamRefresh } from '../../hooks/useStreamRefresh';
import { adaptPositions } from '../../adapters/positions';
import { adaptPortfolio } from '../../adapters/portfolio';
import { Unavailable } from '../Unavailable';

interface PortfolioWorkspaceProps {
  onSelectPosition: (position: Position) => void;
}

/**
 * Portfolio workspace wired to GET /api/v1/positions + /api/v1/portfolio.
 * The client-computed shock-preset simulator is deleted: no stress engine
 * exists server-side, so any number it showed would be invented.
 */
export const PortfolioWorkspace: React.FC<PortfolioWorkspaceProps> = ({
  onSelectPosition,
}) => {
  const [filterClass, setFilterClass] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [localPositions, setLocalPositions] = useState<Position[]>([]);
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);

  // New Position Form State
  const [newSymbol, setNewSymbol] = useState<string>('SOL/USD');
  const [newClass, setNewClass] = useState<'CRYPTO' | 'EQUITY' | 'COMMODITY' | 'FIXED_INCOME'>('CRYPTO');
  const [newSide, setNewSide] = useState<'LONG' | 'SHORT'>('LONG');
  const [newSize, setNewSize] = useState<string>('2500');
  const [newPrice, setNewPrice] = useState<string>('148.20');
  const [newStrategy, setNewStrategy] = useState<string>('Crypto Momentum & Funding Arbitrage');

  // Stream-driven refetch: positions and portfolio valuation are current state, and a
  // stale holdings table is how an operator ends up reasoning about a book that has
  // already changed. Coalesced by useStreamRefresh, so this is not a poller.
  const tick = useStreamRefresh();
  const positionsQuery = useApi(() => portfolioApi.positions(), [tick]);
  const portfolioQuery = useApi(() => portfolioApi.portfolio(), [tick]);

  if (positionsQuery.loading || portfolioQuery.loading) {
    return <div className="text-xs text-slate-400 font-mono p-8">Loading portfolio from /api/v1/positions + /portfolio…</div>;
  }
  if (positionsQuery.error || !positionsQuery.data) {
    return <Unavailable title="Portfolio unavailable" reason={positionsQuery.error ?? "no positions payload"} />;
  }
  if (portfolioQuery.error || !portfolioQuery.data) {
    return <Unavailable title="Portfolio unavailable" reason={portfolioQuery.error ?? "no portfolio payload"} />;
  }

  const adaptedPositions = adaptPositions(positionsQuery.data);
  if ("unavailable" in adaptedPositions) {
    return <Unavailable title="Portfolio unavailable" reason={adaptedPositions.unavailable} />;
  }
  const adaptedAllocation = adaptPortfolio(portfolioQuery.data);
  if ("unavailable" in adaptedAllocation) {
    return <Unavailable title="Portfolio unavailable" reason={adaptedAllocation.unavailable} />;
  }

  const positions = [...localPositions, ...adaptedPositions];
  const totalNotional = positions.reduce((acc, p) => acc + p.notionalUsd, 0);
  const totalUnrealizedPnl = positions.reduce((acc, p) => acc + p.unrealizedPnlUsd, 0);

  const handleAddNewPosition = (e: React.FormEvent) => {
    e.preventDefault();
    const size = parseFloat(newSize) || 0;
    const price = parseFloat(newPrice) || 0;
    const notional = size * price;

    const newPos: Position = {
      id: `local-${Date.now().toString().slice(-4)}`,
      symbol: newSymbol,
      name: `${newSymbol} Asset Position (local only — not sent to backend)`,
      assetClass: newClass as unknown as Position['assetClass'],
      side: newSide,
      size: size,
      entryPrice: price,
      markPrice: price,
      notionalUsd: notional,
      unrealizedPnlUsd: 0,
      unrealizedPnlPct: 0,
      exposurePct: 0,
      strategy: newStrategy,
      originatingAgent: 'Local operator entry',
    };

    setLocalPositions(prev => [newPos, ...prev]);
    setIsAddModalOpen(false);
  };

  const filteredPositions = positions.filter(p => {
    const matchesClass = filterClass === 'ALL' || p.assetClass === filterClass;
    const matchesQuery = p.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         (p.strategy && p.strategy.toLowerCase().includes(searchQuery.toLowerCase())) ||
                         (p.originatingAgent && p.originatingAgent.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesClass && matchesQuery;
  });

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Portfolio Header & Stat Ribbon */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <PieChart className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              PORTFOLIO INTELLIGENCE &amp; POSITION DISPERSION
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">
              FRAME 2 / 15
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Active Holdings: <strong className="text-white">{positions.length} Positions</strong> • NAV ${(portfolioQuery.data.nav / 1000000).toFixed(2)}M • Source: /api/v1/portfolio
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <div className="text-[10px] text-slate-400">TOTAL INVESTED NOTIONAL</div>
            <div className="text-sm font-mono-num font-bold text-white">${(totalNotional / 1000000).toFixed(2)}M</div>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <div className="text-[10px] text-slate-400">NET UNREALIZED P&amp;L</div>
            <div className={`text-sm font-mono-num font-bold flex items-center gap-1 ${totalUnrealizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              <TrendingUp className="w-3.5 h-3.5" />
              {totalUnrealizedPnl >= 0 ? '+' : ''}${(totalUnrealizedPnl / 1000).toFixed(1)}k
            </div>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <div className="text-[10px] text-slate-400">REALIZED P&amp;L (CLOSED)</div>
            <div className="text-sm font-mono-num font-bold text-slate-200">${portfolioQuery.data.realized_pnl.toLocaleString()}</div>
          </div>
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="px-3 py-1.5 rounded bg-cyan-500 hover:bg-cyan-400 text-black font-bold text-xs flex items-center gap-1 shadow-[0_0_12px_rgba(0,240,255,0.4)]"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>ADD HOLDING</span>
          </button>
        </div>
      </div>

      {/* Allocation Map Engine */}
      <CapitalAllocationMap segments={adaptedAllocation} />

      {/* Global Multi-Asset Concentration & Geographic Regime Heatmap */}
      <PortfolioConcentrationHeatmap
        positions={positions}
        onSelectPosition={onSelectPosition}
      />

      {/* Positions Table Filter Bar */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-3.5 shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
          {/* Search */}
          <div className="flex items-center gap-2 bg-black/40 px-3 py-1 rounded border border-white/[0.08] w-72">
            <Search className="w-3.5 h-3.5 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search symbol, strategy, or agent..."
              className="bg-transparent text-xs text-white placeholder-slate-500 focus:outline-none w-full"
            />
          </div>

          {/* Asset Class Filter */}
          <div className="flex flex-wrap items-center gap-1 bg-black/40 p-0.5 rounded border border-white/[0.06] text-[10px]">
            {['ALL', 'POLYMARKET', 'GLOBAL_EQUITY', 'COMMODITY', 'FX', 'US_EQUITY', 'CRYPTO', 'RATES'].map(cls => (
              <button
                key={cls}
                onClick={() => setFilterClass(cls)}
                className={`px-2 py-1 rounded transition-colors uppercase ${
                  filterClass === cls
                    ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-800'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {cls.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>

        {/* Detailed Positions Table */}
        <div className="overflow-x-auto my-2">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-white/[0.06] text-slate-500 text-[9px] uppercase tracking-wider">
                <th className="py-2 px-2.5">SYMBOL</th>
                <th className="py-2 px-2">CLASS</th>
                <th className="py-2 px-2">SIDE</th>
                <th className="py-2 px-2 text-right">SIZE</th>
                <th className="py-2 px-2 text-right">ENTRY</th>
                <th className="py-2 px-2 text-right">MARK</th>
                <th className="py-2 px-2 text-right">NOTIONAL</th>
                <th className="py-2 px-2 text-right">UNREALIZED P&amp;L</th>
                <th className="py-2 px-2 text-right">WEIGHT</th>
                <th className="py-2 px-2">STRATEGY</th>
                <th className="py-2 px-2">AGENT</th>
                <th className="py-2 px-2 text-center">ACTION</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.03]">
              {filteredPositions.map((pos) => {
                const isPos = pos.unrealizedPnlUsd >= 0;
                return (
                  <tr
                    key={pos.id}
                    onClick={() => onSelectPosition(pos)}
                    className="hover:bg-cyan-950/20 cursor-pointer transition-colors group"
                  >
                    <td className="py-2.5 px-2.5 font-bold text-white group-hover:text-cyan-300 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                      {pos.symbol}
                    </td>
                    <td className="py-2.5 px-2 text-slate-400 text-[10px]">{pos.assetClass}</td>
                    <td className="py-2.5 px-2">
                      <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${
                        pos.side === 'LONG'
                          ? 'bg-emerald-950/40 text-emerald-400 border border-emerald-800/50'
                          : 'bg-rose-950/40 text-rose-400 border border-rose-800/50'
                      }`}>
                        {pos.side}
                      </span>
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono-num text-slate-300">
                      {pos.size.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono-num text-slate-400">
                      ${pos.entryPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono-num text-white font-semibold">
                      ${pos.markPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono-num text-slate-200">
                      ${(pos.notionalUsd / 1000).toFixed(1)}k
                    </td>
                    <td className={`py-2.5 px-2 text-right font-mono-num font-bold ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {isPos ? '+' : ''}${pos.unrealizedPnlUsd.toLocaleString()} ({isPos ? '+' : ''}{pos.unrealizedPnlPct.toFixed(2)}%)
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono-num text-slate-300">
                      {(pos.exposurePct || 0).toFixed(2)}%
                    </td>
                    <td className="py-2.5 px-2 text-slate-300 text-[11px] truncate max-w-[120px]">
                      {pos.strategy || '—'}
                    </td>
                    <td className="py-2.5 px-2 text-cyan-400 text-[11px] truncate max-w-[100px]">
                      {pos.originatingAgent || '—'}
                    </td>
                    <td className="py-2.5 px-2 text-center">
                      <span className="text-[10px] text-cyan-400 px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-800/60 group-hover:bg-cyan-900">
                        Inspect
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {filteredPositions.length === 0 && (
          <div className="p-6 text-center text-slate-500 text-xs">
            No open positions. The paper engine holds no positions yet.
          </div>
        )}
      </div>

      {/* Add Holding Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in font-mono">
          <div className="bg-[#0d0f17] border border-cyan-500/40 rounded-md w-full max-w-lg shadow-[0_0_50px_rgba(0,240,255,0.2)] overflow-hidden">
            <div className="p-4 border-b border-white/[0.08] flex items-center justify-between bg-black/40">
              <div className="flex items-center gap-2">
                <Plus className="w-5 h-5 text-cyan-400" />
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  ADD NEW PORTFOLIO POSITION
                </h3>
              </div>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="p-1 rounded text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddNewPosition} className="p-5 space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">Symbol</label>
                  <input
                    type="text"
                    value={newSymbol}
                    onChange={(e) => setNewSymbol(e.target.value)}
                    className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-2 text-white font-mono"
                    required
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">Asset Class</label>
                  <select
                    value={newClass}
                    onChange={(e) => setNewClass(e.target.value as typeof newClass)}
                    className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-2 text-white font-mono"
                  >
                    <option value="POLYMARKET">POLYMARKET PREDICTION</option>
                    <option value="GLOBAL_EQUITY">GLOBAL EQUITY (INTL)</option>
                    <option value="COMMODITY">COMMODITY</option>
                    <option value="FX">FOREX / FX</option>
                    <option value="US_EQUITY">US EQUITY</option>
                    <option value="CRYPTO">CRYPTO / DIGITAL</option>
                    <option value="RATES">RATES / SOVEREIGN</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">Side</label>
                  <select
                    value={newSide}
                    onChange={(e) => setNewSide(e.target.value as typeof newSide)}
                    className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-2 text-white font-mono"
                  >
                    <option value="LONG">LONG</option>
                    <option value="SHORT">SHORT</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">Size / Units</label>
                  <input
                    type="number"
                    step="any"
                    value={newSize}
                    onChange={(e) => setNewSize(e.target.value)}
                    className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-2 text-white font-mono"
                    required
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">Mark Price ($)</label>
                  <input
                    type="number"
                    step="any"
                    value={newPrice}
                    onChange={(e) => setNewPrice(e.target.value)}
                    className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-2 text-white font-mono"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="text-[10px] text-slate-400 block mb-1">Strategy Tag</label>
                <input
                  type="text"
                  value={newStrategy}
                  onChange={(e) => setNewStrategy(e.target.value)}
                  className="w-full bg-black/60 border border-white/[0.1] rounded px-3 py-2 text-white font-mono"
                  required
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 rounded bg-white/[0.04] text-slate-300 hover:text-white"
                >
                  CANCEL
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded bg-cyan-500 hover:bg-cyan-400 text-black font-bold"
                >
                  RECORD POSITION
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
