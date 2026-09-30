import { describe, expect, it } from "vitest";
import { adaptAudit } from "./audit";
import type { AuditRow } from "../api/types";

describe("auditAdapter", () => {
  it("maps audit rows to AuditRecord rows", () => {
    const out = adaptAudit({
      audit: [
        { seq: 7, ts: "2026-09-30T10:00:00Z", kind: "EXECUTION_FILLED", ref_id: "ORD-1", payload: {} },
      ] as AuditRow[],
    });
    expect("unavailable" in out).toBe(false);
    if ("unavailable" in out) return;
    expect(out[0]).toMatchObject({
      seq: 7,
      blockHeight: 7,
      eventType: "EXECUTION_FILLED",
      timestamp: "2026-09-30T10:00:00Z",
      refId: "ORD-1",
      verified: false,
    });
  });

  it("branches on {available:false}", () => {
    expect(adaptAudit({ available: false, reason: "q" })).toEqual({ unavailable: "q" });
  });
});
