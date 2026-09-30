/**
 * resolveSession must branch on data.auth_required: when the server runs open
 * (no API_AUTH_TOKEN set) the console skips login and operates as anonymous
 * VIEWER instead of demanding a junk token. Fail closed on any error.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getIdentity, resolveSession, setIdentity } from "./identity";

function mockSessionMe(body: unknown, ok = true): void {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(body),
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  setIdentity({
    token: "",
    operatorId: "",
    role: "VIEWER",
    authenticated: false,
    authRequired: true,
  });
  vi.restoreAllMocks();
});

describe("resolveSession", () => {
  it("skips login when the server does not require auth", async () => {
    mockSessionMe({
      operator_id: "anonymous",
      role: "VIEWER",
      authenticated: false,
      auth_required: false,
    });
    const identity = await resolveSession();
    expect(identity.authRequired).toBe(false);
    expect(identity.authenticated).toBe(true);
    expect(identity.operatorId).toBe("anonymous");
    expect(identity.role).toBe("VIEWER");
    expect(identity.token).toBe("");
    expect(getIdentity().authenticated).toBe(true);
  });

  it("stays logged out when the server requires auth and no token exists", async () => {
    mockSessionMe({ error: "authentication required" }, false);
    const identity = await resolveSession();
    expect(identity.authRequired).toBe(true);
    expect(identity.authenticated).toBe(false);
  });

  it("fails closed when the backend is unreachable", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("down")) as unknown as typeof fetch;
    const identity = await resolveSession();
    expect(identity.authRequired).toBe(true);
    expect(identity.authenticated).toBe(false);
  });

  it("never clobbers an existing token session", async () => {
    setIdentity({ token: "opaque", authenticated: true, authRequired: true });
    const spy = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ auth_required: false }),
    });
    globalThis.fetch = spy as unknown as typeof fetch;
    const identity = await resolveSession();
    expect(spy).not.toHaveBeenCalled();
    expect(identity.token).toBe("opaque");
    expect(identity.authenticated).toBe(true);
  });
});
