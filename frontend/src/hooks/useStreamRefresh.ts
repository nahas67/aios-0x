import { useEffect, useRef, useState } from 'react';
import { onStream } from '../api/stream';
import {
  DEFAULT_STREAM_REFRESH_MS,
  nextRefreshStamp,
  shouldRefreshOnFrame,
} from '../lib/streamRefresh';

/**
 * A counter that advances when the stream says the world may have moved.
 *
 * Pass it into `useApi`'s deps and the workspace refetches when it advances:
 *
 * ```tsx
 * const tick = useStreamRefresh();
 * const q = useApi(() => riskApi.risk(), [tick]);
 * ```
 *
 * This is how the console stops being frozen at load-time figures without widening the
 * SSE payload and without sixteen workspaces each polling. The decision of *whether* to
 * refetch lives in `lib/streamRefresh.ts`, pure and unit-tested; this hook only supplies
 * the timings and records the stamp.
 *
 * Opt-in rather than wired into `useApi` itself, on purpose. `useApi` serves everything
 * including one-shot fetches that must not repeat — settings, design tokens, a single
 * verification walk. Making it self-refreshing would change the meaning of every existing
 * call site at once, invisibly.
 *
 * The stream is shared, so subscribing here costs one listener, not a connection.
 */
export function useStreamRefresh(minIntervalMs: number = DEFAULT_STREAM_REFRESH_MS): number {
  const [tick, setTick] = useState(0);
  // Refs, not state: these are bookkeeping read inside a listener that must not
  // re-subscribe or re-render on every frame.
  const lastRefreshAt = useRef<number | null>(null);
  const newestFrameAt = useRef<number>(0);

  useEffect(() => {
    // The first tick primes `lastRefreshAt` as "never refetched", so the mount-time
    // fetch is the first refetch and the interval is measured from here.
    lastRefreshAt.current = null;
    newestFrameAt.current = 0;

    const stop = onStream((state) => {
      // The listener receives StreamState, not the frame: `{ status, lastEventAt, frame }`.
      // A status change re-delivers the SAME frame, so the timestamp is compared rather
      // than merely read -- otherwise every reconnect would count as fresh data.
      const frameAt = state.frame?.ts;
      if (typeof frameAt !== 'number') return;
      newestFrameAt.current = frameAt;

      const now = Date.now();
      const allowed = shouldRefreshOnFrame({
        lastRefreshAt: lastRefreshAt.current,
        frameAt,
        now,
        minIntervalMs,
      });
      if (!allowed) return;

      lastRefreshAt.current = nextRefreshStamp(now);
      setTick((previous) => previous + 1);
    });

    return stop;
  }, [minIntervalMs]);

  return tick;
}

export default useStreamRefresh;
