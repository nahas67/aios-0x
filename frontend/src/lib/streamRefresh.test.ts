/**
 * The rate limiter on the stream-driven refetch path.
 *
 * Its failure modes are both bad and both silent, so each is pinned explicitly:
 * refetching on every frame turns a staleness bug into a request storm, and never
 * refetching leaves sixteen workspaces frozen at load-time figures. The coalescing tests
 * below are the ones that matter; the rest pin the edges that a future edit to the
 * interval would silently break.
 */
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_STREAM_REFRESH_MS,
  nextRefreshStamp,
  shouldRefreshOnFrame,
} from './streamRefresh';

const T0 = 1_000_000;

describe('stream-driven refetch', () => {
  it('always fetches the first time, even before any frame', () => {
    // A workspace mounted mid-stream must not wait for the next frame.
    expect(
      shouldRefreshOnFrame({ lastRefreshAt: null, frameAt: T0, now: T0 }),
    ).toBe(true);
  });

  it('does not refetch when no frame arrived since the last one', () => {
    // The guard against an idle stream driving a refetch loop.
    expect(
      shouldRefreshOnFrame({ lastRefreshAt: T0, frameAt: T0, now: T0 + 60_000 }),
    ).toBe(false);
  });

  it('does not refetch for a frame older than the last refetch', () => {
    expect(
      shouldRefreshOnFrame({ lastRefreshAt: T0, frameAt: T0 - 1, now: T0 + 60_000 }),
    ).toBe(false);
  });

  it('refetches once a new frame arrives and the interval has elapsed', () => {
    // 6s, not 2s: the default floor is 5s, so a frame arriving 2s after the last refetch
    // must NOT trigger one. Asserting the positive case at 2s would have required
    // weakening the interval to make the test pass.
    expect(
      shouldRefreshOnFrame({
        lastRefreshAt: T0,
        frameAt: T0 + 6_000,
        now: T0 + 6_000,
      }),
    ).toBe(true);
  });

  it('does not refetch when a frame arrives but the interval has not elapsed', () => {
    expect(
      shouldRefreshOnFrame({ lastRefreshAt: T0, frameAt: T0 + 2_000, now: T0 + 2_000 }),
    ).toBe(false);
  });

  it('coalesces a burst of frames into a single refetch', () => {
    // The storm this module exists to prevent: twenty frames in a burst, one request.
    const lastRefreshAt = T0;
    let allowed = 0;
    for (let i = 1; i <= 20; i += 1) {
      const frameAt = T0 + i * 100; // one frame every 100ms, well inside the interval
      const now = T0 + i * 100;
      if (shouldRefreshOnFrame({ lastRefreshAt, frameAt, now })) allowed += 1;
    }
    // None are allowed until the interval passes, because lastRefreshAt never moved.
    expect(allowed).toBe(0);
  });

  it('allows a refetch per interval as frames keep arriving', () => {
    // Simulates the caller recording the stamp after each allowed refetch.
    let lastRefreshAt: number | null = T0;
    let allowed = 0;
    for (let second = 1; second <= 30; second += 1) {
      const now = T0 + second * 1_000;
      const frameAt = now;
      if (shouldRefreshOnFrame({ lastRefreshAt, frameAt, now })) {
        allowed += 1;
        lastRefreshAt = nextRefreshStamp(now);
      }
    }
    // 30 seconds at a 5s floor = 6 refetches, not 30.
    expect(allowed).toBe(6);
  });

  it('honours a custom interval', () => {
    const args = { lastRefreshAt: T0, frameAt: T0 + 10, now: T0 + 1_000 };
    expect(shouldRefreshOnFrame({ ...args, minIntervalMs: 5_000 })).toBe(false);
    expect(shouldRefreshOnFrame({ ...args, minIntervalMs: 500 })).toBe(true);
  });

  it('defaults to a floor of five seconds', () => {
    expect(DEFAULT_STREAM_REFRESH_MS).toBe(5_000);
    expect(
      shouldRefreshOnFrame({ lastRefreshAt: T0, frameAt: T0 + 1, now: T0 + 4_999 }),
    ).toBe(false);
    expect(
      shouldRefreshOnFrame({ lastRefreshAt: T0, frameAt: T0 + 1, now: T0 + 5_000 }),
    ).toBe(true);
  });

  it('stamps the refetch with now, never with the frame time', () => {
    // Recording frameAt would let a stale frame time suppress a later legitimate
    // refetch, which is a subtle way for the stream to stop updating a workspace.
    expect(nextRefreshStamp(T0 + 9_999)).toBe(T0 + 9_999);
  });

  it('does not refetch while the clock has not advanced past the interval', () => {
    // Two frames at the same instant, as a reconnect burst can deliver.
    expect(
      shouldRefreshOnFrame({ lastRefreshAt: T0, frameAt: T0 + 1, now: T0 }),
    ).toBe(false);
  });
});