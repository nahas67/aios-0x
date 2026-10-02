/**
 * The one way this console renders "nothing here".
 *
 * WHY ONE COMPONENT. Five views had five hand-rolled empty states with three different
 * paddings and two different text colours, and one of them ("No open positions. The paper
 * engine holds no positions yet.") asserted a CAUSE — which an empty array cannot support.
 * An empty result is consistent with "the engine holds none" and with "the engine is down";
 * only the source knows, and usually the source did not answer.
 *
 * The component therefore takes a `SurfaceState` from `lib/stateView.ts` rather than a
 * `rows` array, so it is not possible to render an empty state without having classified the
 * source first. That is the whole design: the honesty lives in the type, not in a prop
 * someone has to remember to set.
 *
 * Absence is styled differently from emptiness on purpose. "We looked, there are none" is a
 * calm fact; "we could not look" is a gap in what the operator knows and must not look like
 * the first.
 */
import React from 'react';
import { Loader2, Inbox, ServerCrash } from 'lucide-react';
import type { SurfaceState } from '../lib/stateView';

export function StateView({
  state,
  noun,
  compact = false,
}: {
  state: SurfaceState;
  noun: string;
  compact?: boolean;
}): React.ReactElement | null {
  if (state.kind === 'ready') return null;

  const pad = compact ? 'py-3 px-3' : 'py-8 px-4';

  if (state.kind === 'loading') {
    return (
      <div className={`${pad} flex items-center justify-center gap-2 text-text-muted`} role="status">
        <Loader2 className="w-3 h-3 animate-spin" aria-hidden />
        <span className="text-xs">Loading {noun}…</span>
      </div>
    );
  }

  if (state.kind === 'unavailable') {
    return (
      <div
        className={`${pad} flex flex-col items-center justify-center gap-1 text-center border border-warning bg-warning-bg rounded`}
        role="alert"
      >
        <div className="flex items-center gap-1.5 text-warning">
          <ServerCrash className="w-3.5 h-3.5" aria-hidden />
          <span className="text-xs font-bold uppercase tracking-wider">{noun} unavailable</span>
        </div>
        {/* The reason, and the standing disclaimer. An operator who sees "0 positions" here
            would conclude the book is empty; they must instead be told we never got to look. */}
        <p className="text-[10px] text-text-muted font-mono">
          {state.observedFrom}: {state.reason}
        </p>
        <p className="text-[10px] text-text-subtle">
          This is not a statement about whether any exist.
        </p>
      </div>
    );
  }

  return (
    <div className={`${pad} flex flex-col items-center justify-center gap-1 text-center`}>
      <div className="flex items-center gap-1.5 text-text-subtle">
        <Inbox className="w-3.5 h-3.5" aria-hidden />
        <span className="text-xs font-bold uppercase tracking-wider">No {noun}</span>
      </div>
      {/* "reported zero" is a claim about the source, and here it is one the source supports. */}
      <p className="text-[10px] text-text-subtle font-mono">{state.observedFrom} reported zero.</p>
    </div>
  );
}
