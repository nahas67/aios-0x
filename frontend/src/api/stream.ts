/**
 * SSE stream client for /api/v1/stream.
 *
 * SECURITY: Uses fetch() with ReadableStream instead of native EventSource
 * because EventSource does NOT support custom Authorization headers.
 *
 * Lifecycle:
 * - auto-connect with exponential reconnect (0.5s → 30s cap)
 * - connection state broadcast to subscribers
 * - heartbeat staleness detection (30s threshold)
 * - clean EOF triggers reconnect when still wanted
 * - 401 places stream in auth-required state (no retry loop)
 * - credential logout/change aborts old stream
 * - proper AbortController cleanup on disconnect/unmount
 */
import type { StreamFrame } from "./types";

export type StreamStatus =
  | "connecting"
  | "live"
  | "reconnecting"
  | "offline"
  | "auth_required";

interface StreamState {
  status: StreamStatus;
  lastEventAt: number | null;
  frame: StreamFrame | null;
}

type Listener = (state: StreamState) => void;

const HEARTBEAT_TIMEOUT_MS = 30_000;

const state: StreamState = { status: "offline", lastEventAt: null, frame: null };
const listeners = new Set<Listener>();
let controller: AbortController | null = null;
let attempt = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let wantConnected = false;
let lastToken = "";

function emit() {
  const snapshot: StreamState = { ...state, frame: state.frame ? { ...state.frame } : null };
  for (const fn of listeners) fn(snapshot);
}

export function onStream(fn: Listener): () => void {
  listeners.add(fn);
  fn({ ...state });
  return () => listeners.delete(fn);
}

function clearTimers() {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (heartbeatTimer !== null) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (state.lastEventAt === null) return;
    const age = Date.now() - state.lastEventAt;
    if (age > HEARTBEAT_TIMEOUT_MS && state.status === "live") {
      state.status = "reconnecting";
      emit();
      abortCurrent();
      scheduleReconnect();
    }
  }, 10_000);
}

function stopHeartbeat() {
  if (heartbeatTimer !== null) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function abortCurrent() {
  if (controller) {
    controller.abort();
    controller = null;
  }
}

function scheduleReconnect() {
  if (!wantConnected) return;
  clearTimers();
  const delay = Math.min(30_000, 500 * 2 ** Math.min(attempt, 6));
  const jitter = delay * 0.2 * Math.random();
  reconnectTimer = setTimeout(connect, delay + jitter);
}

async function connect() {
  if (!wantConnected) return;
  state.status = attempt === 0 ? "connecting" : "reconnecting";
  emit();

  // Import token dynamically to get current value
  const { getIdentity } = await import("../stores/identity");
  const currentToken = getIdentity().token;

  // If token changed, reset attempt counter
  if (currentToken !== lastToken) {
    lastToken = currentToken;
    attempt = 0;
  }

  // No token: connect unauthenticated. If the server requires one it answers
  // 401 and we park in auth_required; an open dev server just streams.

  controller = new AbortController();
  try {
    const headers: Record<string, string> = {
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    };
    if (currentToken) {
      headers.Authorization = `Bearer ${currentToken}`;
    }

    const res = await fetch("/api/v1/stream", {
      headers,
      signal: controller.signal,
    });

    if (!res.ok) {
      if (res.status === 401) {
        state.status = "auth_required";
        state.frame = null;
        emit();
        abortCurrent();
        // Don't retry on auth failure — wait for valid credentials
        return;
      }
      throw new Error(`SSE HTTP ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No ReadableStream");

    attempt = 0;
    state.status = "live";
    state.lastEventAt = Date.now();
    emit();
    startHeartbeat();

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        // Clean EOF — reconnect if we still want connection
        if (wantConnected) {
          state.status = "reconnecting";
          emit();
          stopHeartbeat();
          scheduleReconnect();
        }
        break;
      }
      buffer += decoder.decode(value, { stream: true });

      // Parse SSE lines: "data: {...}\n\n"
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const jsonStr = line.slice(6).trim();
          if (jsonStr) {
            try {
              state.frame = JSON.parse(jsonStr) as StreamFrame;
              state.lastEventAt = Date.now();
              state.status = "live";
              emit();
            } catch {
              // malformed frame: ignore, keep connection
            }
          }
        }
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      // Intentional disconnect
      return;
    }
    // Connection error — schedule reconnect
    if (wantConnected) {
      attempt += 1;
      state.status = "reconnecting";
      emit();
      stopHeartbeat();
      scheduleReconnect();
    }
  } finally {
    controller = null;
    stopHeartbeat();
  }
}

export function startStream(): void {
  if (wantConnected) return;
  wantConnected = true;
  attempt = 0;
  void connect();
}

export function stopStream(): void {
  wantConnected = false;
  clearTimers();
  abortCurrent();
  state.status = "offline";
  emit();
}

/**
 * Called when credentials change (login/logout/switch).
 * Aborts the current stream and reconnects with new credentials.
 */
export function reconnectWithCredentials(): void {
  if (!wantConnected) return;
  abortCurrent();
  clearTimers();
  attempt = 0;
  // Short delay to allow token state to propagate
  setTimeout(() => {
    if (wantConnected) void connect();
  }, 100);
}

export function lastEventAgeMs(): number | null {
  return state.lastEventAt === null ? null : Date.now() - state.lastEventAt;
}
