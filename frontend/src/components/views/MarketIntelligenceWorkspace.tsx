import React from 'react';
import {
  Activity,
  Globe,
  Calendar,
} from 'lucide-react';
import { MarketRegimeField } from '../MarketRegimeField';
import { intelligenceApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { adaptRegimes } from '../../adapters/regimes';
import { Unavailable } from '../Unavailable';

/**
 * Markets workspace wired to GET /api/v1/regimes.
 * The rolling 60-day correlation matrix is deleted: no covariance engine
 * exists server-side, so every coefficient it showed was invented.
 */
export const MarketIntelligenceWorkspace: React.FC = () => {
  const regimesQ = useApi(() => intelligenceApi.regimes());

  if (regimesQ.loading) {
    return <div className="text-xs text-slate-400 font-mono p-8">Loading regimes from /api/v1/regimes…</div>;
  }
  if (regimesQ.error || !regimesQ.data) {
    return <Unavailable title="Markets unavailable" reason={regimesQ.error ?? "no regimes payload"} />;
  }
  const adapted = adaptRegimes(regimesQ.data);
  if ("unavailable" in adapted) {
    return <Unavailable title="Markets unavailable" reason={adapted.unavailable} />;
  }

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              CROSS-ASSET MARKET REGIME & FACTOR FIELD
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 3
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            {adapted.length} labeled symbols • Source: /api/v1/regimes (trend + vol regime only — no price feed)
          </div>
        </div>
      </div>

      {/* State Field */}
      {adapted.length === 0 ? (
        <Unavailable
          title="No regime labels"
          reason="The regime engine has not labeled any symbols yet (it needs at least 5 bars per symbol). This is an honest empty state, not a data gap."
        />
      ) : (
        <MarketRegimeField instruments={adapted} />
      )}

      {/* Grid: Volatility Surface & Term Structure */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* Volatility Structure */}
        <div className="xl:col-span-7 bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                REALIZED VOLATILITY BY SYMBOL (BACKEND-COMPUTED)
              </h3>
            </div>
            <span className="text-[10px] text-slate-400">SOURCE: /api/v1/regimes</span>
          </div>

          <div className="space-y-2.5 py-3 text-xs">
            {regimesQ.data.regimes.map((r) => (
              <div key={r.symbol}>
                <div className="flex justify-between text-slate-400 text-[11px] mb-1">
                  <span>{r.symbol} — {r.trend} / {r.vol_regime} ({r.window_bars ?? 0} bars)</span>
                  <span className="text-cyan-300 font-mono-num font-bold">
                    {r.realized_vol_pct != null ? `${r.realized_vol_pct.toFixed(2)}% realized` : "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Macro Catalysts Feed */}
        <div className="xl:col-span-5 bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                MACRO EVENT PROBABILITY HORIZON
              </h3>
            </div>
            <span className="text-[10px] text-slate-400">NO FEED CONFIGURED</span>
          </div>

          <div className="p-6 text-center text-slate-500 text-xs rounded bg-black/20 border border-dashed border-white/[0.08] mt-2">
            No macro calendar feed is wired. Upcoming catalysts are unknown, not estimated.
          </div>
        </div>
      </div>
    </div>
  );
};
