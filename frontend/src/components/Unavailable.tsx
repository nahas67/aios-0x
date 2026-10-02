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
    <div className="rounded-lg border border-border-subtle bg-[var(--color-surface-1)] p-8 text-center">
      <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-warning bg-warning-bg">
        <Unplug className="h-5 w-5 text-warning" />
      </div>
      <h2 className="text-sm font-semibold uppercase tracking-wider text-text-strong">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-xs leading-relaxed text-text-muted">{reason}</p>
    </div>
  );
};
