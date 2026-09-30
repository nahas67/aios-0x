/**
 * Honest-absence guard shared by every adapter.
 *
 * Backend payloads that can answer absence do it in three shapes:
 * - { available: false, reason }            (all /api/v1/financial/*)
 * - { available: false }                    (/api/v1/knowledge, no reason key)
 * - { available: false, models: [] }        (/api/v1/models and /models/registry)
 * Every adapter branches on this before touching domain fields.
 */

export interface UnavailablePayload {
  available: false;
  reason?: string;
  [key: string]: unknown;
}

export type Unavailable = { unavailable: string };

export function isUnavailable(value: unknown): value is UnavailablePayload {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as Record<string, unknown>).available === false
  );
}

/** Server reason when present, otherwise an honest caller-supplied fallback. */
export function unavailableReason(value: UnavailablePayload, fallback: string): string {
  const reason = value.reason;
  return typeof reason === "string" && reason.length > 0 ? reason : fallback;
}
