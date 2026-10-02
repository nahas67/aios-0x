import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Ban, Check, CircleSlash, Power, ShieldAlert } from 'lucide-react';
import { ControlFailure, runControl } from '../lib/control';
import {
  EMERGENCY_COMMANDS,
  coverageSummary,
  mostDestructiveCommand,
  type EmergencyCommand,
} from '../lib/emergencyCommands';
import { executiveApi } from '../api/backend';

/**
 * The operator surface: ARCHITECTURE.txt §8's human control plane, on its own runtime.
 *
 * WHY THIS IS A SEPARATE ENTRY POINT rather than a tab.
 *
 * §8 requires the eight emergency commands to be deterministic, to bypass AI, to be
 * audited, and to "survive model/runtime failure". The analyst surface cannot host that
 * contract: it opens an SSE stream, mounts sixteen workspaces, and pulls in charting and
 * agent rendering. Any of that failing takes the kill switch down with it — which is
 * precisely the failure §8 names. So this is its own HTML entry, its own bundle, and
 * its own React root. The claim that it shares no runtime with the analyst surface is
 * *measured* in `scripts/verify_operator_isolation.py`, not asserted here.
 *
 * WHAT "SURVIVES FAILURE" DOES AND DOES NOT MEAN, because the weaker reading is a trap.
 * It means the analyst SPA, the SSE stream, the model gateway and the chart bundle may
 * all be broken and this page still renders and still issues a command. It does NOT mean
 * it works with the backend down: the command is a POST to /api/v1/control/{action}, and
 * with no backend there is nothing to authorise it. Pretending otherwise would be the
 * dishonest-panel equivalent of a simulated halt — the exact thing KillSwitchModal's
 * docstring refuses to do.
 *
 * FIRST PAINT MAKES NO NETWORK CALL. The command table is static data
 * (`lib/emergencyCommands`), so the page is readable when the API is unreachable. Liveness
 * is then reported honestly as unknown, then as up or down. An operator opening this
 * page during an incident sees what the system can do and cannot do regardless of
 * whether anything is answering.
 *
 * The five absent commands are rendered as ABSENT, with the reason, and are not
 * disabled buttons. A greyed-out control implies "ask an admin"; these are not
 * implemented anywhere in the tree, and saying so is the only honest rendering.
 */

/** The word an operator must type to authorise the most destructive action. */
const CONFIRM_WORD = 'CONFIRM HALT';

type Reachability = 'unknown' | 'up' | 'down';

function CoverageBadge({ coverage }: { coverage: EmergencyCommand['coverage'] }) {
  if (coverage === 'full') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950/60 border border-emerald-800/60 text-emerald-300">
        <Check className="w-3 h-3" /> AVAILABLE
      </span>
    );
  }
  if (coverage === 'partial') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-950/60 border border-amber-800/60 text-amber-300">
        <AlertTriangle className="w-3 h-3" /> PARTIAL
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-900/80 border border-slate-700/60 text-slate-400">
      <CircleSlash className="w-3 h-3" /> NOT IMPLEMENTED
    </span>
  );
}

export const OperatorSurface: React.FC = () => {
  const [reachability, setReachability] = useState<Reachability>('unknown');
  const [pending, setPending] = useState<string | null>(null);
  const [result, setResult] = useState<{ action: string; ok: boolean; text: string } | null>(null);
  const [confirmation, setConfirmation] = useState('');
  const [armed, setArmed] = useState(false);

  // Liveness only, and only after first paint. Deliberately not a subscription: an
  // operator page that held a stream open could itself become the thing that needs
  // restarting, and this page exists for the moment when everything else is in trouble.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        // `executiveApi` is where `/api/v1/health` lives, which reads oddly on an
        // operator page -- the name describes the module it sits in, not the endpoint.
        // Not worked around by inventing a `healthApi` alias: the bundle-isolation check
        // would then have a new export to allowlist, and the honest statement of "this
        // page needs one method from that module" is the one worth making.
        await executiveApi.health();
        if (!cancelled) setReachability('up');
      } catch {
        if (!cancelled) setReachability('down');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const issue = useCallback(async (command: EmergencyCommand) => {
    const action = command.via[0];
    if (!action) return;
    setPending(action);
    setResult(null);
    try {
      const response = await runControl(action);
      setResult({ action, ok: true, text: JSON.stringify(response) });
      setArmed(false);
      setConfirmation('');
    } catch (err) {
      const text = err instanceof ControlFailure ? err.message : String(err);
      setResult({ action, ok: false, text });
    } finally {
      setPending(null);
    }
  }, []);

  const counts = coverageSummary();
  const destructive = mostDestructiveCommand();

  return (
    <div className="min-h-screen bg-[#08090d] text-[#e2e8f0] font-mono antialiased">
      <div className="max-w-5xl mx-auto px-6 py-10">
        {/* Header */}
        <header className="flex items-start justify-between gap-6 pb-6 border-b border-white/[0.08]">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2.5">
              <ShieldAlert className="w-5 h-5 text-red-400" />
              OPERATOR SURFACE
            </h1>
            <p className="text-[11px] text-slate-500 mt-1">
              ARCHITECTURE.txt §8 — human control plane. Deterministic, bypasses AI,
              audited server-side, separate runtime from the analyst console.
            </p>
          </div>
          <div className="text-right shrink-0">
            <div className="text-[10px] text-slate-500 uppercase">control endpoint</div>
            <div
              className={`text-xs font-bold mt-0.5 ${
                reachability === 'up'
                  ? 'text-emerald-400'
                  : reachability === 'down'
                    ? 'text-red-400'
                    : 'text-slate-500'
              }`}
            >
              {reachability === 'up' ? 'REACHABLE' : reachability === 'down' ? 'UNREACHABLE' : 'UNKNOWN'}
            </div>
          </div>
        </header>

        {/* The honest headline, before any individual command */}
        <div className="my-6 p-4 rounded bg-[#0d0f17] border border-white/[0.08]">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
            <span className="text-slate-400">
              §8 requires <span className="text-white font-bold">8</span> emergency commands.
            </span>
            <span className="text-emerald-400 font-bold">{counts.full} implemented</span>
            <span className="text-amber-400 font-bold">{counts.partial} partial</span>
            <span className="text-slate-400 font-bold">{counts.none} absent</span>
          </div>
          {counts.none > 0 && (
            <p className="mt-2.5 text-[11px] text-slate-400 leading-relaxed border-t border-white/[0.06] pt-2.5">
              <span className="text-amber-400 font-bold">This is a backend gap, not a UI gap.</span>{' '}
              The {counts.none} absent commands have no counterpart anywhere in the tree.
              Containment is global — one kill switch flattens everything — where §8 asks for
              component-level containment. Closing it is an ADR, not a commit; see
              <span className="text-slate-300"> ARCHITECTURE_MAPPING.md §5</span>.
            </p>
          )}
        </div>

        {/* Destructive action, given its own block rather than a row in the table */}
        {destructive && (
          <section className="mb-6 p-5 rounded bg-[#0d0f17] border border-red-800/60 shadow-[0_0_40px_rgba(239,68,68,0.12)]">
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-8 h-8 rounded bg-red-950/80 border border-red-700/60 flex items-center justify-center">
                <Power className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white">{destructive.command}</h2>
                <div className="text-[10px] text-red-400">
                  audited control action: {destructive.via.join(', ')}
                </div>
              </div>
            </div>
            <p className="text-[11px] text-slate-300 mb-3 leading-relaxed">
              {destructive.intent} Flattens every open position at adverse prices, then
              escalates to <span className="text-red-400 font-bold">EMERGENCY_HALT</span>.
              There is no undo from the console; recovery is a separate audited action.
            </p>
            <div className="flex items-center gap-3">
              <input
                type="text"
                value={confirmation}
                onChange={(e) => {
                  setConfirmation(e.target.value);
                  setArmed(e.target.value.trim().toUpperCase() === CONFIRM_WORD);
                }}
                placeholder={CONFIRM_WORD}
                aria-label={`Type ${CONFIRM_WORD} to authorise ${destructive.command}`}
                className="flex-1 px-3 py-2 rounded bg-black/60 border border-red-800/60 text-xs text-red-300 placeholder-slate-600 focus:outline-none focus:border-red-500 font-bold tracking-wider"
              />
              <button
                onClick={() => void issue(destructive)}
                disabled={!armed || pending !== null || reachability === 'down'}
                className={`px-5 py-2 rounded text-xs font-bold tracking-wider transition-colors ${
                  armed && pending === null
                    ? 'bg-red-600 hover:bg-red-500 text-white cursor-pointer'
                    : 'bg-red-950/40 text-red-800 border border-red-950 cursor-not-allowed'
                }`}
              >
                {pending === destructive.via[0] ? 'SENDING…' : 'EXECUTE'}
              </button>
            </div>
          </section>
        )}

        {/* Result of the last action, honest either way */}
        {result && (
          <div
            className={`mb-6 p-3 rounded border text-[11px] leading-relaxed ${
              result.ok
                ? 'bg-emerald-950/30 border-emerald-800/50 text-emerald-200'
                : 'bg-rose-950/40 border-rose-800/60 text-rose-200'
            }`}
          >
            <span className="font-bold">{result.ok ? 'ACCEPTED' : 'REFUSED'}</span>{' '}
            <span className="opacity-80">({result.action})</span>
            <div className="mt-1 opacity-90 break-all">{result.text}</div>
          </div>
        )}

        {/* The full §8 table */}
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="text-[10px] text-slate-500 uppercase border-b border-white/[0.08]">
              <th className="py-2 pr-3 font-normal">command</th>
              <th className="py-2 pr-3 font-normal">intent</th>
              <th className="py-2 pr-3 font-normal">status</th>
              <th className="py-2 pr-3 font-normal">via</th>
            </tr>
          </thead>
          <tbody>
            {EMERGENCY_COMMANDS.map((command) => (
              <tr key={command.command} className="border-b border-white/[0.04] align-top">
                <td className="py-3 pr-3 text-xs font-bold text-white whitespace-nowrap">
                  {command.command}
                </td>
                <td className="py-3 pr-3 text-[11px] text-slate-400">
                  {command.intent}
                  {command.gap && (
                    <div className="mt-1.5 text-slate-500 leading-relaxed max-w-prose">
                      {command.gap}
                    </div>
                  )}
                </td>
                <td className="py-3 pr-3">
                  <CoverageBadge coverage={command.coverage} />
                </td>
                <td className="py-3 pr-3 text-[10px] text-slate-500 font-mono">
                  {command.via.length ? (
                    <>
                      {command.via.join(', ')}
                      <button
                        onClick={() => void issue(command)}
                        disabled={pending !== null || reachability === 'down'}
                        className="ml-2 px-2 py-1 rounded bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed"
                      >
                        {pending === command.via[0] ? '…' : 'RUN'}
                      </button>
                    </>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-slate-600">
                      <Ban className="w-3 h-3" /> none
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <footer className="mt-8 pt-4 border-t border-white/[0.06] text-[10px] text-slate-600 leading-relaxed">
          Every action here POSTs to <span className="text-slate-400">/api/v1/control/&#123;action&#125;</span>{' '}
          and is authorised by the server, which is the sole RBAC authority — this page holds no
          permission of its own and a denial here is the backend's answer, not a UI state. The
          analyst console is a different entry point and a different bundle; it may be entirely
          broken while this page works.
        </footer>
      </div>
    </div>
  );
};

export default OperatorSurface;
