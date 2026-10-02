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
    return <div className="text-xs text-text-muted font-mono p-8">Loading regimes from /api/v1/regimes…</div>;
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
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              CROSS-ASSET MARKET REGIME & FACTOR FIELD
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-info-bg text-accent border border-accent">
              FRAME 3
            </span>
          </div>
          <div className="text-xs text-text-muted mt-0.5">
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
        <div className="xl:col-span-7 bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-2 border-b border-border-subtle">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-accent" />
              <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
                REALIZED VOLATILITY BY SYMBOL (BACKEND-COMPUTED)
              </h3>
            </div>
            <span className="text-[10px] text-text-muted">SOURCE: /api/v1/regimes</span>
          </div>

          <div className="space-y-2.5 py-3 text-xs">
            {regimesQ.data.regimes.map((r) => (
              <div key={r.symbol}>
                <div className="flex justify-between text-text-muted text-[11px] mb-1">
                  <span>{r.symbol} — {r.trend} / {r.vol_regime} ({r.window_bars ?? 0} bars)</span>
                  <span className="text-accent font-mono-num font-bold">
                    {r.realized_vol_pct != null ? `${r.realized_vol_pct.toFixed(2)}% realized` : "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Macro Catalysts Feed */}
        <div className="xl:col-span-5 bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-2 border-b border-border-subtle">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-accent" />
              <h3 className="text-xs font-bold uppercase text-text-strong tracking-wider">
                MACRO EVENT PROBABILITY HORIZON
              </h3>
            </div>
            <span className="text-[10px] text-text-muted">NO FEED CONFIGURED</span>
          </div>

          <div className="p-6 text-center text-text-subtle text-xs rounded bg-surface-sunken border border-dashed border-border-strong mt-2">
            No macro calendar feed is wired. Upcoming catalysts are unknown, not estimated.
          </div>
        </div>
      </div>
    </div>
  );
};
