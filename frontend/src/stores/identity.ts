/**
 * Operator identity — session-scoped presentation state only.
 *
 * SECURITY: The bearer token is NEVER persisted to localStorage or any
 * browser storage. It lives only in JavaScript memory for the duration
 * of the tab session. Closing the tab or refreshing the page clears it.
 *
 * The server resolves identity via /api/v1/session/me. The role and
 * operator_id come from the SERVER, never from the client.
 *
 * AUTH-OPTIONAL: API_AUTH_TOKEN is unset in the default deployment, so the
 * server answers auth_required=false and every route serves anonymous VIEWER.
 * resolveSession() branches on that flag and skips the login screen instead
 * of demanding a junk token. ROLE_LEVEL is declared once here and imported
 * by consumers (e.g. lib/control).
 */
import { useSyncExternalStore } from "react";
import { setAuthToken } from "../api/client";
import { reconnectWithCredentials } from "../api/stream";

export type Role = "VIEWER" | "OPERATOR" | "RISK_ADMIN" | "ADMIN";

export const ROLE_LEVEL: Record<Role, number> = {
  VIEWER: 0,
  OPERATOR: 1,
  RISK_ADMIN: 2,
  ADMIN: 3,
};

export interface Identity {
  operatorId: string;
  role: Role;
  token: string;
  authenticated: boolean;
  /** False when the server runs open (auth_required=false): no login needed. */
  authRequired: boolean;
}

const DEFAULTS: Identity = {
  operatorId: "",
  role: "VIEWER",
  token: "",
  authenticated: false,
  authRequired: true,
};

let identity: Identity = { ...DEFAULTS };
const listeners = new Set<() => void>();

function emit() {
  for (const fn of listeners) fn();
}

/**
 * Set the bearer token and optionally mark as authenticated.
 * Token is kept in memory only — never written to browser storage.
 */
export function setIdentity(next: Partial<Identity>): void {
  const tokenChanged = next.token !== undefined && next.token !== identity.token;
  identity = { ...identity, ...next };
  if (next.token !== undefined) {
    setAuthToken(identity.token);
  }
  emit();
  if (tokenChanged) {
    reconnectWithCredentials();
  }
}

export function getIdentity(): Identity {
  return identity;
}

export function useIdentity(): Identity {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => identity,
  );
}

interface SessionMe {
  operator_id?: string;
  role?: string;
  authenticated?: boolean;
  auth_required?: boolean;
}

/**
 * Resolve the session against GET /api/v1/session/me with no credentials.
 * Open server (auth_required=false) → operate as anonymous VIEWER, no login.
 * Locked server → stay logged out until authenticateWithToken succeeds.
 * Any failure fails closed (authRequired=true, authenticated=false).
 * Never clobbers an existing token session.
 */
export async function resolveSession(): Promise<Identity> {
  if (getIdentity().token) return getIdentity();
  try {
    const res = await fetch("/api/v1/session/me");
    if (!res.ok) {
      setIdentity({ authenticated: false, authRequired: true });
      return getIdentity();
    }
    const data = (await res.json()) as SessionMe;
    if (data.auth_required === false) {
      setIdentity({
        token: "",
        operatorId: data.operator_id || "anonymous",
        role: "VIEWER",
        authenticated: true,
        authRequired: false,
      });
    } else {
      setIdentity({ authenticated: false, authRequired: true });
    }
  } catch {
    setIdentity({ authenticated: false, authRequired: true });
  }
  return getIdentity();
}

/**
 * Authenticate: call /api/v1/session/me to get server-resolved identity.
 * Returns true if authentication succeeded.
 */
export async function authenticateWithToken(token: string): Promise<boolean> {
  setAuthToken(token);
  try {
    const res = await fetch("/api/v1/session/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      setAuthToken("");
      setIdentity({ token: "", authenticated: false, operatorId: "", role: "VIEWER" });
      return false;
    }
    const data = (await res.json()) as SessionMe;
    setIdentity({
      token,
      authenticated: true,
      operatorId: data.operator_id || "",
      role: (data.role || "VIEWER") as Role,
      authRequired: true,
    });
    return true;
  } catch {
    setAuthToken("");
    setIdentity({ token: "", authenticated: false, operatorId: "", role: "VIEWER" });
    return false;
  }
}

/**
 * Logout: clear all identity state.
 */
export function logout(): void {
  setAuthToken("");
  setIdentity({ token: "", authenticated: false, operatorId: "", role: "VIEWER" });
}
