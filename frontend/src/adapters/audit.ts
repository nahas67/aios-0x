/**
 * auditAdapter: /api/v1/audit rows → zip AuditRecord rows.
 * Per-row verified/proof fields have no source in /audit; verified stays
 * false and chain truth comes from /api/v1/audit/verify instead.
 */
import type { AuditRow } from "../api/types";
import type { AuditRecord } from "../types";
import { type Unavailable } from "./absent";

export function adaptAudit(
  payload: { audit: AuditRow[] } | { available: false; reason?: string },
): AuditRecord[] | Unavailable {
  if ("available" in payload) {
    const reason = payload.reason;
    return { unavailable: typeof reason === "string" && reason.length > 0 ? reason : "audit log unavailable" };
  }
  return payload.audit.map((row) => {
    const rawActor = row.payload?.actor ?? row.payload?.actor_id;
    const actor = typeof rawActor === "string" && rawActor.length > 0 ? rawActor : "—";
    const summary = `${row.kind}${row.ref_id ? ` · ${row.ref_id}` : ""}`;
    return {
      id: `AUD-${row.seq}`,
      seq: row.seq,
      blockHeight: row.seq,
      eventType: row.kind,
      timestamp: row.ts,
      kind: row.kind,
      refId: row.ref_id ?? undefined,
      actor,
      prevHash: "",
      verified: false,
      summary,
      actionSummary: summary,
      payload: row.payload,
    };
  });
}
