/**
 * The executive reconciliation decisions behind `useLiveExecutive`.
 *
 * Every test here is paired with its opposite, because the failure mode these
 * functions exist to prevent is a *plausible* wrong answer rather than a crash:
 * a frozen figure labelled live, a poll silently overriding a healthy stream, or a
 * malformed frame blanking a good value. A test that only checks the happy path
 * would pass against implementations with any of those bugs.
 *
 * The stream status is an input rather than something derived from the data,
 * because `/api/v1/stream` reports its own state and the client should not
 * second-guess it from a payload's contents.
 */
import { describe, expect, it } from "vitest";

import type { StreamStatus } from "../api/stream";
import type { Executive, StreamFrame } from "../api/types";

import {
  frameExecutive,
  reconcileExecutive,
  shouldPoll,
} from "./executiveReconcile";

const EMPTY: Executive = {
  cash_balance: 0,
  open_positions: 0,
  cumulative_realized_pnl: 0,
  closed_trades: 0,
  emergency_state: "NORMAL",
  drawdown_pct: null,
  chain_valid: true,
  events_logged: 0,
  predictions_scored: 0,
  postmortems: 0,
  paused: null,
};

const STALE: Executive = { ...EMPTY, open_positions: 99, events_logged: 1_234 };
const FRESH: Executive = { ...EMPTY, open_positions: 3, events_logged: 9_999 };

function frame(executive: Executive): StreamFrame {
  return { ts: 0, executive, platform_tail: [] };
}

const NONE = { executive: null, source: null } as const;

describe("reconcileExecutive", () => {
  it("shows the frame and calls it live when the stream is live", () => {
    const view = reconcileExecutive(NONE, "live", frame(FRESH), null);
    expect(view.executive).toBe(FRESH);
    expect(view.source).toBe("stream");
  });

  it("does not let a poll override a healthy stream", () => {
    // The opposite of the previous test: a poll that lands while the stream is
    // live must NOT be shown, or the panel flickers between two sources on every
    // poll tick while the numbers are equally fresh.
    const view = reconcileExecutive(NONE, "live", frame(FRESH), STALE);
    expect(view.executive).toBe(FRESH);
    expect(view.source).toBe("stream");
  });

  it("shows the poll once the stream is not live, and does not call it live", () => {
    // A stream that dropped but a poll has landed: the poll is the more recent
    // value, and the label must not claim stream delivery.
    const view = reconcileExecutive(NONE, "reconnecting", null, FRESH);
    expect(view.executive).toBe(FRESH);
    expect(view.source).toBe("poll");
  });

  it("keeps the last frame when the stream dropped and no poll has landed", () => {
    // Showing nothing here would be worse than showing something slightly stale:
    // "no data" is a different claim from "the last thing the server said".
    const view = reconcileExecutive(NONE, "reconnecting", frame(FRESH), null);
    expect(view.executive).toBe(FRESH);
    expect(view.source).not.toBe("stream");
  });

  it("prefers the poll over a stale frame once both exist and the stream is down", () => {
    const view = reconcileExecutive(NONE, "auth_required", frame(STALE), FRESH);
    expect(view.executive).toBe(FRESH);
    expect(view.source).toBe("poll");
  });

  it("reports null source before anything has arrived", () => {
    expect(reconcileExecutive(NONE, "offline", null, null)).toEqual(NONE);
  });

  it("does not invent an executive when the frame is empty", () => {
    // A missing frame must not produce a partially-filled object; the panel
    // shows "no data" rather than zeros, because zeros here would read as a
    // real measurement.
    const view = reconcileExecutive(NONE, "live", null, null);
    expect(view.executive).toBeNull();
    expect(view.source).toBeNull();
  });

  it("is idempotent: the same inputs give the same answer", () => {
    const once = reconcileExecutive(NONE, "live", frame(FRESH), STALE);
    const twice = reconcileExecutive(once, "live", frame(FRESH), STALE);
    expect(twice).toEqual(once);
  });

  it("does not mutate the view it is given", () => {
    const current = { executive: STALE, source: "poll" as const };
    const snapshot = { ...current };
    reconcileExecutive(current, "live", frame(FRESH), null);
    expect(current).toEqual(snapshot);
  });
});

describe("shouldPoll", () => {
  const STATUSES: StreamStatus[] = [
    "connecting",
    "live",
    "reconnecting",
    "offline",
    "auth_required",
  ];

  it("polls for every status except live", () => {
    for (const status of STATUSES) {
      expect(shouldPoll(status)).toBe(status !== "live");
    }
  });

  it("keeps polling while auth_required, because that is when state is most wanted", () => {
    // The stream parks in auth_required when the server rejects its credentials.
    // A live-only design would show nothing in exactly the situation where an
    // operator most wants to see what the system is doing.
    expect(shouldPoll("auth_required")).toBe(true);
  });

  it("keeps polling while reconnecting, because a reconnect can take 30s", () => {
    expect(shouldPoll("reconnecting")).toBe(true);
  });

  it("stops polling only when live", () => {
    expect(shouldPoll("live")).toBe(false);
  });
});

describe("frameExecutive", () => {
  it("passes a well-formed executive through unchanged", () => {
    // `/api/v1/stream` builds its payload from `builder.executive()`, the same
    // call `/api/v1/executive` serves, so no translation happens. This test
    // pins that: if a translation layer ever appears, this fails rather than the
    // screen quietly showing reshaped numbers.
    expect(frameExecutive(frame(FRESH))).toBe(FRESH);
  });

  it("returns null for a missing frame", () => {
    expect(frameExecutive(null)).toBeNull();
  });

  it("returns null for a frame with no executive", () => {
    expect(frameExecutive({ ts: 0, platform_tail: [] } as unknown as StreamFrame)).toBeNull();
  });

  it("returns null when the executive is not an object", () => {
    // A malformed frame must not put `undefined` on screen where a number is
    // expected; that reads as a measurement of zero.
    expect(
      frameExecutive({ ts: 0, executive: "boom", platform_tail: [] } as unknown as StreamFrame),
    ).toBeNull();
  });

  it("does not reject a partial executive, because the server owns its shape", () => {
    // The frame is whatever `builder.executive()` produced. Filtering its fields
    // here would silently drop a field the server adds later, which is a quieter
    // failure than showing it.
    const partial = { open_positions: 4 } as unknown as Executive;
    expect(frameExecutive({ ts: 0, executive: partial, platform_tail: [] })).toBe(partial);
  });
});