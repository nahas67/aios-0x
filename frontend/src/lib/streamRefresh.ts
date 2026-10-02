/**
 * Deciding when a stream frame should cause a workspace to refetch.
 *
 * WHY THIS EXISTS. `api/server.py` pushes a frame every two seconds carrying `executive`
 * and `platform_tail`. Only `SystemHealthWorkspace` consumed it; the other sixteen
 * workspaces call `useApi`, which loads once on mount and again when its deps change.
 * Their figures are therefore as-of-load, with nothing on screen saying so — a
 * staleness problem, not a polling problem (there is no polling; see
 * ARCHITECTURE_MAPPING.md §7).
 *
 * WHY NOT SIMPLY REFETCH ON EVERY FRAME. Sixteen workspaces on a two-second cadence is
 * roughly eight requests per second against an API whose `/financial/*` routes hit
 * SQLite with `synchronous = FULL`. Adopting the stream naively would trade a staleness
 * bug for a self-inflicted load problem, which is worse because it is self-inflicted and
 * invisible until the store starts timing out.
 *
 * WHY NOT WIDEN THE PAYLOAD. Not needed for this, and it is a contract change: it puts
 * more work on a two-second hot loop for every client, including ones that want only one
 * resource. A frame arriving is already a sufficient signal that something moved, so the
 * fix belongs on the consumer side.
 *
 * THE RULE. Refetch when a frame has arrived since the last refetch AND the minimum
 * interval has elapsed. Both conditions, not either:
 *
 *   - frame-after-last-refetch prevents a refetch loop on an idle stream, where frames
 *     keep arriving but nothing has changed since the workspace last looked;
 *   - the interval coalesces a burst of frames into one refetch, so a backlog replay or
 *     a reconnect that delivers twenty frames quickly costs one request, not twenty.
 *
 * Pure and dependency-free so it can be tested directly: this is a rate limiter on a
 * safety-relevant read path, and the interesting behaviour is all in the timing edges.
 */

/** Default floor between refetches triggered by the stream, in milliseconds. */
export const DEFAULT_STREAM_REFRESH_MS = 5_000;

/** What the decider needs to know. Kept as one object so the arguments cannot swap. */
export interface RefreshDecisionInput {
  /** Epoch ms of the last refetch, or null if this workspace has never refetched. */
  lastRefreshAt: number | null;
  /** Epoch ms carried by the newest frame seen since the last decision. */
  frameAt: number;
  /** Epoch ms now. */
  now: number;
  /** Floor between refetches. */
  minIntervalMs?: number;
}

export function shouldRefreshOnFrame(input: RefreshDecisionInput): boolean {
  const { lastRefreshAt, frameAt, now } = input;
  const minIntervalMs = input.minIntervalMs ?? DEFAULT_STREAM_REFRESH_MS;

  // First look: always fetch, so a workspace mounted mid-stream still gets data rather
  // than waiting for the next frame that may be seconds away.
  if (lastRefreshAt === null) return true;

  // Nothing new since the last refetch. This is the guard that stops an idle stream from
  // driving a refetch loop, and it is why the frame timestamp is compared to the refetch
  // timestamp rather than merely checked for existence.
  if (frameAt <= lastRefreshAt) return false;

  return now - lastRefreshAt >= minIntervalMs;
}

/**
 * The next `lastRefreshAt` after a refresh, for the caller to record.
 *
 * `now`, not `frameAt`: the refetch reflects everything up to the moment it ran, and
 * recording the frame time instead would let a stale frame time suppress a later,
 * legitimate refresh.
 */
export function nextRefreshStamp(now: number): number {
  return now;
}
