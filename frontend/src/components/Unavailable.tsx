import React from 'react';
import { Unplug } from 'lucide-react';

interface UnavailableProps {
  /** Server-provided reason, or an honest placeholder until adapters land. */
  reason: string;
  title?: string;
}

/**
 * Shared honest-absence state. Every backend payload that can answer
 * {available: false} renders through here with its reason — never an
 * invented empty book, never fake numbers.
 */
export const Unavailable: React.FC<UnavailableProps> = ({ reason, title = 'Unavailable' }) => {
  return (
    <div className="rounded-lg border border-white/[0.07] bg-[#0d0f17] p-8 text-center">
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-amber-700/50 bg-amber-950/40">
        <Unplug className="h-5 w-5 text-amber-300" />
      </div>
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-xs leading-relaxed text-slate-400">{reason}</p>
    </div>
  );
};
