/**
 * Chat response -> view model. Pure, no React, no DOM.
 *
 * WHY THIS IS A SEPARATE MODULE. There is no DOM test environment in this project: no
 * jsdom, no happy-dom, no react-test-renderer, and no `.tsx` test exists. Adding one would
 * mean adding dependencies, which this repo admits only behind an ADR. So the renderable
 * decision is extracted here and tested directly, and `ChatPanel` only maps a
 * `ChatView` onto elements.
 *
 * That is the same move `streamRefresh.ts` made for the SSE refetch, for the same reason:
 * the logic worth testing should not require a browser to reach.
 *
 * THE INVARIANT THIS MODULE EXISTS TO HOLD
 * =========================================
 * `toChatView` returns data, and the data contains no functions, no callbacks and no
 * dispatch table. That is deliberate and it is the whole safety argument for showing an
 * agent's suggested actions in the UI: there is nothing executable to hand the renderer, on
 * this side OR the server side (`core/agent_advisory.py` holds no control-plane
 * reference). `chatView.test.ts` deep-walks the result and asserts no value is callable, so
 * "suggested actions are inert" is a checked property rather than a comment.
 *
 * Tone is derived, never passed in. A caller cannot label a denial as neutral.
 */

export type ChatTone = 'neutral' | 'positive' | 'destructive' | 'warning';

export interface EvidenceView {
  readonly label: string;
  readonly source: string;
  readonly available: boolean;
  readonly detail: string;
}

export interface AdvisoryChatView {
  readonly kind: 'advisory';
  readonly tone: ChatTone;
  readonly title: string;
  readonly agent: string | null;
  readonly body: string;
  /** RECORDED | MODEL | UNKNOWN — how the text was produced, shown as a badge. */
  readonly stance: string;
  /** Always prefixed so the operator reads it as provenance, not as a result. */
  readonly attribution: string;
  readonly evidence: readonly EvidenceView[];
  /** NAMES only. Nothing consumes them; there is no dispatch table in the codebase. */
  readonly suggestions: readonly string[];
  readonly limitations: readonly string[];
}

export interface ReceiptChatView {
  readonly kind: 'command';
  readonly tone: ChatTone;
  readonly title: string;
  readonly action: string;
  readonly body: string;
  readonly payload: unknown;
}

export interface DenialChatView {
  readonly kind: 'denied';
  readonly tone: ChatTone;
  readonly title: string;
  readonly action: string;
  readonly body: string;
}

export interface PlainChatView {
  readonly kind: 'help' | 'query' | 'error' | 'unknown';
  readonly tone: ChatTone;
  readonly title: string;
  readonly body: string;
}

export type ChatView = AdvisoryChatView | ReceiptChatView | DenialChatView | PlainChatView;

const ADVISORY_PREFIX = 'It would suggest (not executed)';

function str(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

/** Stance drives tone. UNKNOWN is destructive because it is the "we could not tell you" case. */
function toneForStance(stance: string): ChatTone {
  if (stance === 'UNKNOWN') return 'destructive';
  return 'neutral';
}

export function toChatView(response: unknown): ChatView {
  if (!response || typeof response !== 'object') {
    return { kind: 'unknown', tone: 'neutral', title: 'Unreadable response', body: '' };
  }
  const raw = response as Record<string, unknown>;
  const kind = str(raw.kind, 'unknown');
  const answer = str(raw.answer);

  if (kind === 'advisory') {
    const advisory = (raw.advisory ?? {}) as Record<string, unknown>;
    const attribution = (advisory.attribution ?? {}) as Record<string, unknown>;
    const stance = str(advisory.stance, 'UNKNOWN');
    const evidence = Array.isArray(advisory.evidence) ? advisory.evidence : [];
    const suggestions = Array.isArray(advisory.proposed_actions)
      ? advisory.proposed_actions.filter((s): s is string => typeof s === 'string')
      : [];
    const limitations = Array.isArray(advisory.limitations)
      ? advisory.limitations.filter((s): s is string => typeof s === 'string')
      : [];

    // The model name belongs with the mode it came from: "model (test-model) — synthesised".
    // Joining all three with one separator produced "model — (test-model) — …", which reads
    // as three unrelated fields.
    const mode = str(attribution.mode, 'deterministic');
    const attributionText =
      [attribution.model ? `${mode} (${str(attribution.model)})` : mode, str(attribution.note)]
        .filter(Boolean)
        .join(' — ');

    return {
      kind: 'advisory',
      tone: toneForStance(stance),
      title: [str(advisory.agent_id), str(advisory.community), str(advisory.role)]
        .filter(Boolean)
        .join(' · ') || 'Advisory',
      agent: typeof raw.agent === 'string' ? raw.agent : null,
      body: answer,
      stance,
      attribution: attributionText || 'unspecified',
      evidence: evidence.map((item) => {
        const ref = (item ?? {}) as Record<string, unknown>;
        return {
          label: str(ref.label, str(ref.source, 'view')),
          source: str(ref.source),
          available: ref.available !== false,
          detail: str(ref.detail),
        };
      }),
      // The prefix lives in the view model, not the component, so a suggestion cannot be
      // rendered without its "not executed" label even if the JSX is later rearranged.
      suggestions: suggestions.map((name) => `${ADVISORY_PREFIX}: ${name}`),
      limitations,
    };
  }

  if (kind === 'command') {
    const action = str(raw.action, 'unknown');
    return {
      kind: 'command',
      tone: 'positive',
      title: `Control action executed: ${action}`,
      action,
      body: 'Authorized under your role and written to the audit log.',
      payload: raw.result ?? null,
    };
  }

  if (kind === 'denied') {
    const action = str(raw.action, 'unknown');
    return {
      kind: 'denied',
      tone: 'destructive',
      title: `Denied: ${action}`,
      action,
      body: answer,
    };
  }

  if (kind === 'help') {
    return { kind: 'help', tone: 'neutral', title: 'What I understand', body: answer };
  }

  if (kind === 'query') {
    return { kind: 'query', tone: 'neutral', title: str(raw.query, 'Result'), body: answer };
  }

  if (kind === 'error') {
    return { kind: 'error', tone: 'destructive', title: 'Error', body: answer };
  }

  // An unrecognised `kind` is shown as-is rather than dropped. A new server-side kind must
  // not render as an empty bubble.
  return { kind: 'unknown', tone: 'warning', title: `Unrecognised response: ${kind}`, body: answer };
}

export function isAdvisory(view: ChatView): view is AdvisoryChatView {
  return view.kind === 'advisory';
}
