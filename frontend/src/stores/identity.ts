/**
 * Operator identity — session-scoped presentation state only.
 *
 * SECURITY: The bearer token is NEVER persisted to localStorage or any
 * browser storage. It lives only in JavaScript memory for the duration
 * of the tab session. Closing the tab or refreshing the page clears it.
 *
 * The server resolves identity via /api/v1/session/me. The role and
 * operator_id come from the SERVER, never from the client.
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
}

const DEFAULTS: Identity = {
  operatorId: "",
  role: "VIEWER",
  token: "",
  authenticated: false,
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
    const data = await res.json();
    setIdentity({
      token,
      authenticated: true,
      operatorId: data.operator_id || "",
      role: (data.role || "VIEWER") as Role,
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
