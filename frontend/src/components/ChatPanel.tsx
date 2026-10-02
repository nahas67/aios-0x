/**
 * Operator chat, including asking a named agent for a sourced opinion.
 *
 * THE ONE RULE THIS UI ENFORCES
 * =============================
 * An advisory is never dressed up as an action. `lib/chatView.ts` decides what a response
 * looks like, and it deliberately produces no callbacks — so there is nothing here to wire a
 * suggested action to. Each suggestion renders as an inert chip whose label already says
 * "not executed", because the prefix lives in the view model rather than the JSX: a
 * suggestion cannot be displayed without that label even if this markup is rearranged.
 *
 * There is no server-side dispatch for those strings either — `core/agent_advisory.py`
 * imports neither the control plane nor any order sink. So a "Run this" button would be a
 * lie about a capability that does not exist. An operator who wants one types the command,
 * which then runs through the audited control path under their own role.
 *
 * WHY A COMMAND RENDERS AS A RECEIPT. `kind === "command"` means a control action was
 * authorized and executed. It is shown with its action name and its payload, never as a
 * chatty "Done!" — a trading console that says "Done!" has told the operator something they
 * cannot verify.
 *
 * Tokens only. Colours come from the ADR-008 token layer, so this panel is themed by the
 * same switch as the rest of the console and contains no colour literal of its own.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Send, Loader2, ShieldCheck, TriangleAlert, CircleHelp, Bot, ListChecks } from 'lucide-react';
import { controlApi } from '../api/backend';
import type { ChatResponse } from '../api/types';
import { ApiError } from '../api/client';
import { isAdvisory, toChatView, type ChatTone, type ChatView } from '../lib/chatView';

interface Turn {
  id: number;
  from: 'operator' | 'console';
  text: string;
  view?: ChatView;
  failure?: string;
}

const EXAMPLES: readonly string[] = [
  'pnl',
  'ask strategy what is leaning toward',
  'ask memory how is it scoring us',
  'show me the gates',
];

let seq = 0;
const nextId = () => (seq += 1);

export default function ChatPanel(): React.ReactElement {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // Keep the newest turn in view; an operator reading an answer should not have to scroll
    // to find it.
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns]);

  const send = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || busy) return;

      setTurns((prev) => [...prev, { id: nextId(), from: 'operator', text: trimmed }]);
      setDraft('');
      setBusy(true);
      try {
        // Only `message` is sent: the server resolves identity and role from its own token
        // map and ignores the body, so passing them would imply client-side authority that
        // does not exist.
        const response = (await controlApi.chat({ message: trimmed })) as ChatResponse;
        setTurns((prev) => [...prev, { id: nextId(), from: 'console', text: '', view: toChatView(response) }]);
      } catch (err) {
        // A failure is shown as itself. Substituting a canned "something went wrong" would
        // hide whether the backend was unreachable or the request was rejected.
        const detail = err instanceof ApiError ? `${err.message} (HTTP ${err.status})` : String(err);
        setTurns((prev) => [...prev, { id: nextId(), from: 'console', text: '', failure: detail }]);
      } finally {
        setBusy(false);
      }
    },
    [busy],
  );

  return (
    // A viewport-relative height, not `h-full`: this panel mounts inside a `main` that has
    // no resolved height (it is `flex-1` with a `min-h`), so `h-full` computes to `auto`
    // and the scroll area collapses to nothing — leaving a header and an input with no log
    // between them. The offset clears the fixed top bar plus the main element's padding.
    <section className="flex flex-col h-[calc(100vh-7.5rem)] min-h-[24rem] bg-surface-0 text-text">
      <header className="flex items-start gap-2 px-4 py-3 border-b border-border-subtle">
        <ShieldCheck className="w-4 h-4 mt-0.5 text-accent shrink-0" aria-hidden />
        <div className="min-w-0">
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-strong">Operator Chat</h2>
          <p className="text-[10px] text-text-muted mt-0.5">
            Questions are read-only. Commands run through the audited control path under your own role.
            An agent can advise; it cannot act.
          </p>
        </div>
      </header>

      <div ref={logRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {turns.length === 0 && (
          <div className="text-[11px] text-text-subtle space-y-1">
            <p>Try one of these:</p>
            <ul className="space-y-0.5">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => void send(example)}
                    className="text-accent hover:underline font-mono"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {turns.map((turn) => (
          <TurnView key={turn.id} turn={turn} />
        ))}

        {busy && (
          <div className="flex items-center gap-2 text-[11px] text-text-muted">
            <Loader2 className="w-3 h-3 animate-spin" aria-hidden />
            <span>Consulting…</span>
          </div>
        )}
      </div>

      <form
        className="flex items-center gap-2 px-4 py-3 border-t border-border-subtle"
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="pnl · ask strategy what is leaning · pause trading"
          aria-label="Message"
          disabled={busy}
          className="flex-1 bg-surface-1 border border-border-subtle rounded px-3 py-2 text-xs text-text placeholder:text-text-subtle focus:border-accent focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          aria-label="Send"
          className="px-3 py-2 rounded bg-info-bg text-accent border border-accent text-xs font-bold disabled:opacity-40 flex items-center gap-1"
        >
          <Send className="w-3 h-3" aria-hidden />
          Send
        </button>
      </form>
    </section>
  );
}

function TurnView({ turn }: { turn: Turn }): React.ReactElement | null {
  if (turn.from === 'operator') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] px-3 py-2 rounded bg-surface-raised border border-border-subtle text-xs text-text-strong font-mono">
          {turn.text}
        </div>
      </div>
    );
  }
  if (turn.failure) {
    return (
      <div className="flex items-start gap-2 px-3 py-2 rounded bg-destructive-bg border border-destructive text-xs text-destructive-soft">
        <TriangleAlert className="w-3.5 h-3.5 mt-0.5 shrink-0" aria-hidden />
        <span>{turn.failure}</span>
      </div>
    );
  }
  if (!turn.view) return null;

  const view = turn.view;
  const icon =
    view.kind === 'advisory' ? (
      <Bot className="w-3.5 h-3.5 mt-0.5 shrink-0 text-accent" aria-hidden />
    ) : view.kind === 'command' ? (
      <ListChecks className="w-3.5 h-3.5 mt-0.5 shrink-0" aria-hidden />
    ) : view.kind === 'denied' || view.kind === 'error' ? (
      <TriangleAlert className="w-3.5 h-3.5 mt-0.5 shrink-0" aria-hidden />
    ) : view.kind === 'help' ? (
      <CircleHelp className="w-3.5 h-3.5 mt-0.5 shrink-0" aria-hidden />
    ) : null;

  const badge = isAdvisory(view) ? view.stance : undefined;

  return (
    <Card tone={view.tone} icon={icon} title={view.title} badge={badge}>
      <p className="text-[11px] text-text mb-2 whitespace-pre-line">{view.body}</p>

      {isAdvisory(view) && (
        <>
          {/* Attribution sits directly under the answer, because it decides how much weight
              that answer deserves. */}
          <p className="text-[10px] text-text-subtle mb-2">
            <span className="uppercase tracking-wider">Produced by</span>{' '}
            <span className="text-text-muted">{view.attribution}</span>
          </p>

          {view.evidence.length > 0 && (
            <div className="mb-2">
              <div className="text-[10px] uppercase tracking-wider text-text-subtle mb-1">Read from</div>
              <ul className="space-y-0.5">
                {view.evidence.map((ref) => (
                  <li key={`${ref.source}-${ref.label}`} className="text-[10px] font-mono">
                    <span className="text-text-muted">{ref.label}</span>{' '}
                    <span className="text-text-subtle">({ref.source})</span>{' '}
                    <span className={ref.available ? 'text-positive' : 'text-text-dim'}>{ref.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {view.suggestions.length > 0 && (
            <div className="mb-2">
              <div className="text-[10px] uppercase tracking-wider text-text-subtle mb-1">
                Advisory suggestions
              </div>
              <div className="flex flex-wrap gap-1">
                {/* Inert spans, never buttons: the view model supplies no dispatch. */}
                {view.suggestions.map((suggestion) => (
                  <span
                    key={suggestion}
                    className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-surface-sunken border border-border-subtle text-text-muted"
                  >
                    {suggestion}
                  </span>
                ))}
              </div>
            </div>
          )}

          {view.limitations.length > 0 && (
            <ul className="space-y-0.5 border-t border-border-faint pt-2">
              {view.limitations.map((limitation) => (
                <li key={limitation} className="text-[10px] text-text-subtle">
                  · {limitation}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {view.kind === 'command' && (
        <pre className="text-[10px] font-mono text-text bg-surface-sunken border border-border-subtle rounded p-2 overflow-x-auto">
          {JSON.stringify(view.payload, null, 2)}
        </pre>
      )}
    </Card>
  );
}

const TONE: Record<ChatTone, { border: string; badge: string }> = {
  neutral: { border: 'border-border-subtle', badge: 'bg-surface-raised text-text-muted border-border-subtle' },
  positive: { border: 'border-positive', badge: 'bg-positive-bg text-positive border-positive' },
  destructive: { border: 'border-destructive', badge: 'bg-destructive-bg text-destructive-soft border-destructive' },
  warning: { border: 'border-warning', badge: 'bg-warning-bg text-warning border-warning' },
};

function Card({
  tone,
  icon,
  title,
  badge,
  children,
}: {
  tone: ChatTone;
  icon?: React.ReactNode;
  title: string;
  badge?: string;
  children: React.ReactNode;
}): React.ReactElement {
  const style = TONE[tone];
  return (
    <div className={`px-3 py-2 rounded bg-surface-1 border ${style.border}`}>
      <div className="flex items-start gap-2 mb-1">
        {icon}
        <span className="text-[11px] font-bold text-text-strong flex-1 min-w-0">{title}</span>
        {badge && (
          <span
            className={`text-[9px] px-1.5 py-0.5 rounded border font-bold uppercase tracking-wider shrink-0 ${style.badge}`}
          >
            {badge}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
