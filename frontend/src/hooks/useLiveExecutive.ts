/**
 * useLiveExecutive — the executive snapshot, live when the stream is up.
 *
 * WHY THIS EXISTS. `/api/v1/stream` has been served since G210, and
 * `api/stream.ts` has implemented a correct, authenticated, reconnecting client
 * since the same commit — and nothing ever called `startStream()`. The server
 * pushed an executive snapshot every two seconds to nobody. This is the piece
 * that consumes it.
 *
 * THE DECISIONS LIVE IN `executiveReconcile.ts`, not here. The frontend has no
 * component-test framework, so a hook's inline logic is untestable logic; the
 * decisions are therefore pure functions with tests, and this is the wiring.
 * What remains untested — that React re-renders on the right signal — is stated
 * as untested rather than assumed covered.
 *
 * POLLING IS THE FALLBACK, NOT THE REMOVAL. While the stream is not live this
 * hook polls `executiveApi.get()` on an interval, deliberately:
 *
 *   - the stream parks in `auth_required` whenever the server answers 401, which
 *     it does for an unauthenticated console, and a live-only hook would show
 *     nothing in exactly the situation where an operator most wants state;
 *   - a reconnect can take 30 seconds, and during it a live-only hook shows a
 *     frozen number with no hint that it is frozen — which is worse than a slower
 *     one, because a stale figure presented as current is the failure mode
 *     `CONSTITUTION.md` section 3 is about.
 */
import { useCallback, useEffect, useState } from "react";

import { executiveApi } from "../api/backend";
import { lastEventAgeMs, onStream, startStream, stopStream } from "../api/stream";
import type { StreamStatus } from "../api/stream";
import type { Executive, StreamFrame } from "../api/types";

import { frameExecutive, reconcileExecutive, shouldPoll } from "./executiveReconcile";
import type { ExecutiveSource, ExecutiveView } from "./executiveReconcile";

/** Matches the server's SSE tick (api/server.py `_stream(interval_s=2.0)`). */
export const POLL_INTERVAL_MS = 5_000;

/** The view before anything has arrived. A constant, so identity is stable. */
const EMPTY_VIEW: ExecutiveView = { executive: null, source: null };

export interface LiveExecutive {
  executive: Executive | null;
  /** Where `executive` came from. Null before anything has arrived. */
  source: ExecutiveSource;
  /** The stream's own status, verbatim. Not inferred from the data. */
  status: StreamStatus;
  /** True only when the stream is `live`; false means the value is polled. */
  live: boolean;
  /**
   * Milliseconds since the last stream frame, or null if none has arrived.
   *
   * Recomputed on a tick while the stream is NOT live, so a parked feed's age
   * keeps counting rather than freezing at the value it held when the stream last
   * spoke. It froze before, which meant a console whose stream had been dead for
   * minutes displayed the age from minutes ago -- a stale figure presented as
   * current, in the one readout whose entire job is to say how current the
   * figure beside it is.
   */
  lastFrameAgeMs: number | null;
  /** When the last frame arrived, or null. The fact; `lastFrameAgeMs` is a reading. */
  lastFrameAt: number | null;
  refresh: () => void;
}

export type { ExecutiveSource };

export function useLiveExecutive(
  pollIntervalMs: number = POLL_INTERVAL_MS,
): LiveExecutive {
  const [status, setStatus] = useState<StreamStatus>("offline");
  const [frame, setFrame] = useState<StreamFrame | null>(null);
  const [polled, setPolled] = useState<Executive | null>(null);
  const [lastFrameAgeMs, setLastFrameAgeMs] = useState<number | null>(null);
  const [lastFrameAt, setLastFrameAt] = useState<number | null>(null);

  const poll = useCallback(async () => {
    try {
      setPolled(await executiveApi.get());
    } catch {
      // A failed poll is not evidence that the previous snapshot became wrong.
      // Leaving it in place reports "the last known value"; blanking the panel
      // would report "no data", which is a different and less true statement.
    }
  }, []);

  // The stream is a module-level singleton keyed on `wantConnected`, so starting
  // it here is idempotent across every consumer.
  useEffect(() => {
    startStream();
    return () => stopStream();
  }, []);

  useEffect(() => {
    void poll();
  }, [poll]);

  // `onStream` replays current state on subscribe, so this also picks up a
  // stream that was already live before this component mounted.
  useEffect(() => onStream((next) => {
    setStatus(next.status);
    setLastFrameAgeMs(lastEventAgeMs());
    setLastFrameAt(Date.now());
    // A frame is adopted only if it actually carries an executive. A malformed
    // frame is ignored rather than allowed to replace a good value with
    // `undefined`, which on screen reads as a measurement of zero.
    const executive = frameExecutive(next.frame);
    if (executive) setFrame({ ...next.frame!, executive });
  }), []);

  // Recomputed from the inputs on every change rather than inside the handlers,
  // so no transition can be missed by a listener that did not fire.
  // Derived from the inputs rather than held separately: two sources of truth for
  // "what is on screen" can disagree, and a client keeping its own copy of a
  // server value is the shape of defect #42.
  const view = reconcileExecutive(EMPTY_VIEW, status, frame, polled);

  // The interval stays mounted across status changes: tearing it down and back up
  // on every blink would itself become a request storm.
  useEffect(() => {
    if (!shouldPoll(status)) return;
    const id = setInterval(() => {
      void poll();
      // Keep the age counting while the feed is parked. A poll refreshes the
      // executive value but NOT the stream's frame time, so without this the
      // readout freezes at whatever it showed when the stream last spoke.
      setLastFrameAgeMs(lastEventAgeMs());
    }, pollIntervalMs);
    return () => clearInterval(id);
  }, [status, poll, pollIntervalMs]);

  return {
    executive: view.executive,
    source: view.source,
    status,
    live: status === "live",
    lastFrameAgeMs,
    lastFrameAt,
    refresh: poll,
  };
}