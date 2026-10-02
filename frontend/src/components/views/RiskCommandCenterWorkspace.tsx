import React from 'react';
import { RiskSpectrum } from '../../types';
import {
  ShieldAlert,
  Scale
} from 'lucide-react';
import { RiskCommandSpectrum } from '../RiskCommandSpectrum';
import { riskApi, settingsApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { useStreamRefresh } from '../../hooks/useStreamRefresh';
import { adaptRisk } from '../../adapters/risk';
import { Unavailable } from '../Unavailable';

/**
 * Risk workspace wired to GET /api/v1/risk + /api/v1/settings (thresholds).
 * The macro stress-test scenario simulator is deleted: research/disaster.py
 * is fetcher chaos-testing, not a stress engine, so every simulated
 * drawdown it showed was invented.
 */
export const RiskCommandCenterWorkspace: React.FC = () => {
  // Refetched when the stream says state may have moved, coalesced to at most one
  // request per interval. Risk state is the figure an operator acts on and the one most
  // dangerous to read stale: a drawdown that has since crossed 3% would otherwise keep
  // rendering as within tolerance, with nothing on screen to say when it was measured.
  // Settings are deliberately NOT subscribed -- thresholds change on human action, and a
  // stream refetch would suggest otherwise.
  const tick = useStreamRefresh();
  const riskQ = useApi(() => riskApi.risk(), [tick]);
  const settingsQ = useApi(() => settingsApi.settings());

  if (riskQ.loading || settingsQ.loading) {
    return <div className="text-xs text-slate-400 font-mono p-8">Loading risk state from /api/v1/risk…</div>;
  }
  if (riskQ.error || !riskQ.data) {
    return <Unavailable title="Risk unavailable" reason={riskQ.error ?? "no risk payload"} />;
  }

  const adapted = adaptRisk(riskQ.data, settingsQ.data?.risk ?? null);
  if ("unavailable" in adapted) {
    return <Unavailable title="Risk unavailable" reason={adapted.unavailable} />;
  }
  const risk: RiskSpectrum = adapted.spectrum;

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              INSTITUTIONAL RISK COMMAND CENTER & FIREWALL
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 7
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            State: {riskQ.data.current_state ?? "—"} • Locked out: {String(riskQ.data.locked_out ?? "—")} • Source: /api/v1/risk
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">DRAWDOWN:</span>{' '}
            <span className="text-white font-bold">{risk.currentDrawdownPct.toFixed(2)}%</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">HARD CEILING:</span>{' '}
            <span className="text-red-400 font-bold">{risk.emergencyHaltPct.toFixed(2)}% MAX DRAWDOWN</span>
          </div>
        </div>
      </div>

      {/* Main Continuous Risk Spectrum */}
      <RiskCommandSpectrum risk={risk} notComputed={adapted.notComputed} />

      {adapted.notComputed.length > 0 && (
        <div className="text-[11px] text-slate-500 font-mono px-1">
          Not computed by the backend: {adapted.notComputed.join(", ")} — shown as "—", never estimated.
        </div>
      )}

      {/* Recent transitions + compliance alerts from the live payload */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
          <h3 className="text-xs font-bold uppercase text-white tracking-wider pb-3 border-b border-white/[0.06]">
            RECENT GOVERNOR TRANSITIONS ({riskQ.data.recent_transitions.length})
          </h3>
          <div className="mt-2 space-y-1.5 text-xs">
            {riskQ.data.recent_transitions.length === 0 && (
              <div className="text-slate-500">No transitions recorded.</div>
            )}
            {riskQ.data.recent_transitions.map((t, i) => (
              <div key={i} className="p-2 rounded bg-white/[0.02] border border-white/[0.05]">
                <div className="font-bold text-slate-200">{t.new_state}</div>
                <div className="text-[11px] text-slate-400">{t.reason}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Tiered Drawdown Constitution Rules */}
        <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <Scale className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                CONSTITUTIONAL DRAWDOWN TIERS
              </h3>
            </div>
            <span className="text-[10px] text-emerald-400">RATIFIED v1.0.0</span>
          </div>

          <div className="space-y-2.5 my-3 text-xs">
            <div className="p-2 rounded bg-emerald-950/20 border border-emerald-800/40">
              <div className="flex justify-between font-bold text-emerald-300 text-xs">
                <span>TIER 0: NOMINAL REGIME</span>
                <span>0.00% – {risk.warningThresholdPct.toFixed(2)}%</span>
              </div>
              <div className="text-[10px] text-slate-300 mt-1">
                Full autonomous multi-agent execution permitted. 100% position limit capacity.
              </div>
            </div>

            <div className="p-2 rounded bg-amber-950/20 border border-amber-800/40">
              <div className="flex justify-between font-bold text-amber-300 text-xs">
                <span>TIER 1: ELEVATED WARNING</span>
                <span>{risk.warningThresholdPct.toFixed(2)}% – {risk.reductionThresholdPct.toFixed(2)}%</span>
              </div>
              <div className="text-[10px] text-slate-300 mt-1">
                Halts new position openings. Automated 25% proportional trim on highest volatility assets.
              </div>
            </div>

            <div className="p-2 rounded bg-orange-950/20 border border-orange-800/40">
              <div className="flex justify-between font-bold text-orange-300 text-xs">
                <span>TIER 2: AGGRESSIVE DE-RISKING</span>
                <span>{risk.reductionThresholdPct.toFixed(2)}% – {risk.emergencyHaltPct.toFixed(2)}%</span>
              </div>
              <div className="text-[10px] text-slate-300 mt-1">
                Autonomous 50% liquidation across risk assets into USD cash / short-term T-bills.
              </div>
            </div>

            <div className="p-2 rounded bg-red-950/20 border border-red-800/40">
              <div className="flex justify-between font-bold text-red-300 text-xs">
                <span>TIER 3: EMERGENCY HALT (KILL SWITCH)</span>
                <span>&gt; {risk.emergencyHaltPct.toFixed(2)}%</span>
              </div>
              <div className="text-[10px] text-slate-300 mt-1">
                Complete position flattening. Halts all agent inference. Requires human Compliance Officer + CIO sign-off.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
