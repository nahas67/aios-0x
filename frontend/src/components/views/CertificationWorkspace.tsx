import React from 'react';
import { Award, Ban, CheckCircle2, ShieldAlert, XCircle } from 'lucide-react';
import { portfolioApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { useStreamRefresh } from '../../hooks/useStreamRefresh';
import { Unavailable } from '../Unavailable';
import type { ClaimGateState } from '../../api/types';

/**
 * Layer 7 — the STRATEGY CERTIFICATION FIREWALL, as a screen.
 *
 * WHY THIS VIEW HAD TO BE BUILT AT ALL. The endpoint existed, the response types
 * existed, and the API client method existed — nothing rendered it. A certification gate
 * that computes a verdict and shows it to no one is not a gate an operator can rely on,
 * and §2 makes Layer 7 the thing that decides whether anything may trade. The data was
 * plumbed and dark.
 *
 * THE DESIGN POINT, and the reason this is not a scorecard.
 *
 * A criterion here has TWO independent results, and the view must never let them blur:
 *
 *   1. Did it clear its threshold?  `pass` — current vs threshold.
 *   2. May the number be quoted as a result?  `claim.status` — all fourteen required
 *      provenance fields present, or it is NOT_REPORTABLE.
 *
 * These come apart constantly. A Sharpe of 1.6 against a 1.0 threshold PASSES, and is
 * still NOT_REPORTABLE, because it has no defined universe, no out-of-sample window and
 * no confidence interval. Rendering that as a green tick beside the figure is precisely
 * the misrepresentation §11 exists to prevent — a measured number wearing the clothes of
 * a result. So `pass` and `reportable` are separate columns, and a figure that passes
 * while being unreportable is shown as exactly that.
 *
 * `ready_for_live` is typed `false` at the API boundary and is not a computed field
 * here: live routing is constitutionally disabled in this release, so the view states
 * that rather than implying it is waiting on a metric.
 */
export const CertificationWorkspace: React.FC = () => {
  // The gate verdict is derived from live paper metrics, so a stale verdict is a stale
  // claim about whether anything may trade. Stream-driven, coalesced. Kept on a shorter
  // interval than the default because this is the screen an operator checks before
  // acting, and it is a single cheap aggregate endpoint.
  const tick = useStreamRefresh(5_000);
  const gradQ = useApi(() => portfolioApi.graduation(), [tick]);

  if (gradQ.loading) {
    return (
      <div className="text-xs text-text-muted font-mono p-8">
        Loading certification gate from /api/v1/graduation…
      </div>
    );
  }
  if (gradQ.error || !gradQ.data) {
    return (
      <Unavailable
        title="Certification gate unavailable"
        reason={gradQ.error ?? 'no graduation payload'}
      />
    );
  }

  const grad = gradQ.data;
  const status = grad.claim_status;

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Verdict */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <ShieldAlert className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold tracking-wider text-text-strong uppercase">
              LAYER 7 · STRATEGY CERTIFICATION FIREWALL
            </h2>
          </div>
          <ClaimBadge state={status} />
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat
            label="ready for live"
            value="NO"
            tone="red"
            // Not waiting on a metric. Constitutional, per this release.
            note="constitutionally disabled, not pending"
          />
          <Stat
            label="paper criteria"
            value={grad.paper_criteria_pass ? 'PASS' : 'FAIL'}
            tone={grad.paper_criteria_pass ? 'green' : 'red'}
            note="thresholds only, no provenance"
          />
          <Stat
            label="criteria checked"
            value={String(grad.criteria.length)}
            tone="slate"
            note="each gated separately"
          />
          <Stat
            label="required fields"
            value={`${grad.required_fields.length}`}
            tone="slate"
            note="from the §11 claim gate"
          />
        </div>

        {grad.note && (
          <p className="mt-3 text-[11px] leading-relaxed text-text-muted border-t border-border-subtle pt-3">
            {grad.note}
          </p>
        )}
      </div>

      {/* Checks: threshold verdict and reportability, side by side and never merged */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md overflow-hidden">
        <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
          <h3 className="text-[11px] font-bold tracking-wider text-text uppercase">
            CRITERIA
          </h3>
          <span className="text-[9px] text-text-subtle">
            threshold verdict and reportability are separate questions
          </span>
        </div>

        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="text-[9px] text-text-subtle uppercase border-b border-border-subtle">
              <th className="px-4 py-2 font-normal">criterion</th>
              <th className="px-4 py-2 font-normal text-right">current</th>
              <th className="px-4 py-2 font-normal text-right">threshold</th>
              <th className="px-4 py-2 font-normal">threshold verdict</th>
              <th className="px-4 py-2 font-normal">may be quoted?</th>
            </tr>
          </thead>
          <tbody>
            {grad.criteria.map((criterion) => (
              <tr
                key={criterion.name}
                className="border-b border-border-subtle align-top text-[11px]"
              >
                <td className="px-4 py-3 text-text-strong">{criterion.name}</td>
                <td className="px-4 py-3 text-right text-text-strong font-mono">
                  {criterion.current}
                </td>
                <td className="px-4 py-3 text-right text-text-subtle font-mono">
                  {criterion.op} {criterion.threshold}
                </td>
                <td className="px-4 py-3">
                  {criterion.pass ? (
                    <span className="inline-flex items-center gap-1 text-positive">
                      <CheckCircle2 className="w-3.5 h-3.5" /> within threshold
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-destructive">
                      <XCircle className="w-3.5 h-3.5" /> outside threshold
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <ClaimBadge state={criterion.claim.status} compact />
                  {criterion.claim.missing.length > 0 && (
                    <div className="mt-1.5 text-text-subtle leading-relaxed">
                      missing:{' '}
                      <span className="text-text-muted">
                        {criterion.claim.missing.join(', ')}
                      </span>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* The refusal reason, in full. §11's fourteen fields, and which are absent. */}
      <div className="bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4">
        <div className="flex items-center gap-2 mb-3">
          <Award className="w-4 h-4 text-accent" />
          <h3 className="text-[11px] font-bold tracking-wider text-text uppercase">
            REQUIRED PROVENANCE (§11)
          </h3>
        </div>
        <p className="text-[10px] text-text-subtle mb-3 leading-relaxed">
          A figure is REPORTABLE only when every one of these is present. A number
          without them may be shown, never quoted as a result.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {grad.required_fields.map((field) => (
            <span
              key={field}
              className="px-2 py-1 rounded text-[10px] font-mono bg-surface-veil border border-border-subtle text-text-muted"
            >
              {field}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

/** REPORTABLE / NOT_REPORTABLE / NO_CLAIM. Never collapsed to a single colour. */
function ClaimBadge({
  state,
  compact = false,
}: {
  state: ClaimGateState['status'];
  compact?: boolean;
}) {
  const map = {
    REPORTABLE: { cls: 'bg-positive-bg border-positive text-positive', Icon: CheckCircle2 },
    NOT_REPORTABLE: { cls: 'bg-warning-bg border-warning text-warning', Icon: Ban },
    NO_CLAIM: { cls: 'bg-surface-deep border-border-subtle text-text-muted', Icon: XCircle },
  } as const;
  const { cls, Icon } = map[state];
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${cls}`}
    >
      <Icon className="w-3 h-3" />
      {state}
      {!compact && <span className="opacity-60">· claim gate</span>}
    </span>
  );
}

function Stat({
  label,
  value,
  tone,
  note,
}: {
  label: string;
  value: string;
  tone: 'red' | 'green' | 'slate';
  note: string;
}) {
  const toneCls = {
    red: 'text-destructive',
    green: 'text-positive',
    slate: 'text-text-strong',
  }[tone];
  return (
    <div className="bg-surface-sunken border border-border-subtle rounded p-3">
      <div className="text-[9px] uppercase text-text-subtle">{label}</div>
      <div className={`text-lg font-bold mt-0.5 ${toneCls}`}>{value}</div>
      <div className="text-[9px] text-text-subtle mt-0.5">{note}</div>
    </div>
  );
}

export default CertificationWorkspace;