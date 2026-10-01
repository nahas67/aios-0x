/**
 * Executive reconciliation — the decisions behind `useLiveExecutive`, as pure
 * functions.
 *
 * WHY THIS IS A SEPARATE MODULE. The frontend has no component-test framework:
 * no `@testing-library/react`, no `jsdom`, no `happy-dom`. So a hook cannot be
 * rendered in a test, and a hook whose logic lives only inside it is a hook whose
 * logic is untested. Extracting the decisions makes them checkable, and the hook
 * becomes a thin wrapper over them.
 *
 * This is the same seam the model-governance adapter established: test the
 * decision, not the framework that applies it. What remains untested — that React
 * re-renders on the right signal — is stated as untested rather than assumed.
 *
 * THE TWO DECISIONS
 *
 *   1. Which snapshot is on screen, and where it came from.
 *   2. Whether the fallback poll should be running.
 *
 * Both have a non-obvious correct answer, which is why they are written down
 * rather than inlined.
 */
import type { StreamStatus } from "../api/stream";
import type { Executive, StreamFrame } from "../api/types";

/**
 * Where the value on screen came from.
 *
 * Three states, not two. `stream` and `poll` are both LIVE -- a value delivered
 * this instant by one or the other. `stream_stale` is neither: the stream
 * delivered it, and the stream has since stopped, so the figure is the last thing
 * the server said rather than something currently arriving.
 *
 * An independent review found the two-state version returning `"poll"` for a
 * stream-delivered value whenever no poll had landed yet, which the UI renders as
 * FALLBACK POLL. So a console parked in `auth_required` was told its state came
 * from a fallback poll that had not run -- the mirror image of the dishonesty this
 * module exists to prevent, and committed in the same commit that named it.
 *
 * A separate label rather than an overloading of `"poll"` because "polled" and
 * "stale" are different facts: the first says where the number came from, the
 * second says how much to trust it now.
 */
export type ExecutiveSource = "stream" | "poll" | "stream_stale" | null;

export interface ExecutiveView {
  executive: Executive | null;
  source: ExecutiveSource;
}

/**
 * Decide what the consumer sees, given the last frame and the last poll.
 *
 * `frame` wins when it exists, even if the stream has since dropped: it is the
 * last thing the server actually said. The `source` label does NOT follow the
 * value in that case — it reports `"stream"` only while the stream is `live`, so a
 * label claiming live delivery for a value delivered before a disconnect would be
 * an overstatement. A consumer that cares about currency reads `lastFrameAgeMs`
 * for that, which is why it is reported separately rather than folded in here.
 *
 * A poll never overrides a live stream's value. Otherwise every poll that landed
 * during a reconnect would visibly downgrade the panel and then upgrade it
 * again, which reads as instability in a number that is merely refreshing.
 */
export function reconcileExecutive(
  current: ExecutiveView,
  status: StreamStatus,
  frame: StreamFrame | null,
  polled: Executive | null,
): ExecutiveView {
  const live = status === "live";

  if (live && frame) {
    return { executive: frame.executive, source: "stream" };
  }
  if (frame && !polled) {
    // Stream dropped, nothing polled yet: keep the last thing the server said.
    // Reported as stream_stale, NOT as "poll" -- a fallback poll has not run, and
    // claiming it had tells the operator where a number came from when nobody
    // knows.
    return { executive: frame.executive, source: "stream_stale" };
  }
  if (frame && polled) {
    // Stream down and a poll has landed: the poll is the more recent of the two,
    // so it is what is on screen. Reported as "poll" because the stream is not
    // the source of what is displayed.
    return { executive: polled, source: "poll" };
  }
  if (polled) {
    return { executive: polled, source: current.source ?? "poll" };
  }
  return current;
}

/**
 * Whether the fallback poll should be running.
 *
 * `live` is the only status that stops it. In particular `auth_required` keeps
 * polling: that state means the server rejected the credentials for the *stream*,
 * and a live-only design would show nothing in exactly the situation where an
 * operator most wants to see state. `reconnecting` likewise polls, because a
 * reconnect can take up to 30 seconds.
 */
export function shouldPoll(status: StreamStatus): boolean {
  return status !== "live";
}

/**
 * Whether a frame's executive can be shown as-is.
 *
 * `/api/v1/stream` builds its payload from `builder.executive()`, the same call
 * `/api/v1/executive` serves, so a frame's executive IS an `Executive` and no
 * translation is involved. This exists to make that assumption explicit and
 * testable rather than implicit: a null or non-object executive is a malformed
 * frame, and it must not replace a good value with `undefined` on screen.
 */
export function frameExecutive(frame: StreamFrame | null): Executive | null {
  const value = frame?.executive;
  if (!value || typeof value !== "object") return null;
  return value;
}