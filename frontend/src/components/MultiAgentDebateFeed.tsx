import React, { useState } from 'react';
import {
  BrainCircuit,
  Scale,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  MessageSquare,
  TrendingUp,
  TrendingDown,
  Filter,
  Search,
  Copy,
  Check,
} from 'lucide-react';
import { debatesApi } from '../api/backend';
import { useApi } from '../hooks/useApi';
import { adaptDebates, type DebateSessionView } from '../adapters/debates';
import { Unavailable } from './Unavailable';

interface MultiAgentDebateFeedProps {
  className?: string;
  onInspectAgent?: (agentId: string) => void;
}

/**
 * Debate feed wired to GET /api/v1/debates. Sessions render turn-by-turn
 * exactly as the backend recorded them; with no sessions (e.g.
 * MODEL_PROVIDER=none) the feed reports honest absence. There is no replay
 * simulation: turns are historical records, not a live stream.
 */
export const MultiAgentDebateFeed: React.FC<MultiAgentDebateFeedProps> = ({
  className = '',
  onInspectAgent
}) => {
  const debatesQ = useApi(() => debatesApi.debates());
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (debatesQ.loading) {
    return <div className="text-xs text-text-muted font-mono p-8">Loading debates from /api/v1/debates…</div>;
  }
  if (debatesQ.error || !debatesQ.data) {
    return <Unavailable title="Debates unavailable" reason={debatesQ.error ?? "no debates payload"} />;
  }
  const adapted = adaptDebates(debatesQ.data);
  if ("unavailable" in adapted) {
    return <Unavailable title="No debates recorded" reason={adapted.unavailable} />;
  }
  const sessions: DebateSessionView[] = adapted;

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Filtered list of sessions
  const filteredSessions = sessions.filter(session => {
    if (searchQuery === '') return true;
    const q = searchQuery.toLowerCase();
    return (
      (session.symbol ?? '').toLowerCase().includes(q) ||
      session.id.toLowerCase().includes(q) ||
      session.turns.some(t => t.thesis.toLowerCase().includes(q) || t.agentId.toLowerCase().includes(q))
    );
  });

  const activeSession =
    sessions.find(s => s.id === selectedSessionId) || filteredSessions[0] || sessions[0] || null;

  // Helper for stance formatting
  const getStanceBadge = (stance: string) => {
    const upper = stance.toUpperCase();
    if (upper.includes('LONG') || upper.includes('PROPOSE')) {
      return {
        label: stance,
        bg: 'bg-positive-bg',
        text: 'text-positive',
        border: 'border-positive',
        icon: <TrendingUp className="w-3 h-3 text-positive" />
      };
    }
    if (upper.includes('SHORT') || upper.includes('HEDGE')) {
      return {
        label: stance,
        bg: 'bg-destructive-bg',
        text: 'text-destructive',
        border: 'border-destructive',
        icon: <TrendingDown className="w-3 h-3 text-destructive" />
      };
    }
    if (upper.includes('CHALLENGE') || upper.includes('RISK')) {
      return {
        label: stance,
        bg: 'bg-warning-bg',
        text: 'text-warning',
        border: 'border-warning',
        icon: <AlertTriangle className="w-3 h-3 text-warning" />
      };
    }
    if (upper.includes('SYNTHESIS') || upper.includes('CONSENSUS') || upper.includes('RESOL')) {
      return {
        label: stance,
        bg: 'bg-positive-bg',
        text: 'text-positive',
        border: 'border-positive',
        icon: <CheckCircle2 className="w-3 h-3 text-positive" />
      };
    }
    if (upper.includes('FIREWALL') || upper.includes('VERIF') || upper.includes('AUDIT')) {
      return {
        label: stance,
        bg: 'bg-violet',
        text: 'text-violet',
        border: 'border-violet',
        icon: <ShieldCheck className="w-3 h-3 text-violet" />
      };
    }
    return {
      label: stance,
      bg: 'bg-surface-veil',
      text: 'text-text',
      border: 'border-border-strong',
      icon: <BrainCircuit className="w-3 h-3 text-accent" />
    };
  };

  return (
    <div className={`bg-[var(--color-surface-1)] border border-border-strong rounded-md p-4 shadow-2xl space-y-4 font-mono ${className}`}>
      {/* Top Header & Overview */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-border-subtle">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded bg-info-bg border border-accent text-accent">
              <BrainCircuit className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold tracking-wider text-text-strong uppercase">
                  MULTI-AGENT DEBATE &amp; ADVERSARIAL CONSENSUS FEED
                </h3>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-surface-veil text-text-muted border border-border-strong font-semibold">
                  RECORDED SESSIONS
                </span>
              </div>
              <p className="text-xs text-text-muted mt-0.5">
                Source: /api/v1/debates • Turns are recorded history, not a live stream
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-xs text-text-muted flex items-center gap-1.5">
            <span>DEBATE SESSIONS:</span>
            <span className="text-accent font-bold font-mono-num">{sessions.length} RECORDED</span>
          </div>
          <button
            onClick={() => debatesQ.refresh()}
            className="px-2.5 py-1 rounded bg-surface-veil hover:bg-surface-raised border border-border-strong text-text text-[10px] transition-colors"
          >
            REFRESH
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-surface-sunken p-2 rounded border border-border-subtle">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] text-text-subtle uppercase mr-1 flex items-center gap-1">
            <Filter className="w-3 h-3 text-text-subtle" /> RECORDED TURNS ONLY
          </span>
        </div>

        <div className="relative min-w-[220px]">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-text-subtle" />
          <input
            type="text"
            placeholder="Search debate thesis, symbol..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-surface-deep border border-border-strong rounded pl-8 pr-3 py-1 text-xs text-text-strong placeholder-text-subtle focus:outline-none focus:border-accent font-mono"
          />
        </div>
      </div>

      {sessions.length === 0 ? (
        <Unavailable
          title="No debates recorded"
          reason="The backend holds no debate sessions (recorded transcripts only exist in memory during replay)."
        />
      ) : (
        <>
          {/* Debate Session Selection Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {filteredSessions.map((session) => {
              const isSelected = session.id === activeSession?.id;
              const isShort = session.side === 'SHORT' || session.side === 'HEDGE';

              return (
                <div
                  key={session.id}
                  onClick={() => setSelectedSessionId(session.id)}
                  className={`p-3 rounded border transition-all cursor-pointer relative overflow-hidden ${
                    isSelected
                      ? 'bg-surface-raised border-accent shadow-[0_0_15px_rgba(0,240,255,0.12)]'
                      : 'bg-surface-veil hover:bg-surface-veil border-border-subtle hover:border-border-subtle'
                  }`}
                >
                  {isSelected && (
                    <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-accent via-positive to-accent" />
                  )}

                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-bold text-text-strong tracking-wide">{session.symbol ?? session.id}</span>
                        <span className={`text-[9px] px-1 py-0.2 rounded border font-semibold ${
                          isShort ? 'bg-destructive-bg text-destructive border-destructive' : 'bg-positive-bg text-positive border-positive'
                        }`}>
                          {session.side}
                        </span>
                      </div>
                      <div className="text-[11px] text-text-muted font-mono line-clamp-1 mt-0.5">
                        {session.id}
                      </div>
                    </div>

                    <div className="text-right">
                      <span className="text-xs font-bold text-accent font-mono-num">
                        {session.consensusScorePct !== null ? `${session.consensusScorePct.toFixed(1)}%` : "—"}
                      </span>
                      <div className="text-[9px] text-text-muted font-normal">CONSENSUS</div>
                    </div>
                  </div>

                  <div className="mt-2.5 pt-2 border-t border-border-subtle flex items-center justify-between text-[10px] text-text-muted">
                    <span>{session.turns.length} TURNS</span>
                    <span className="px-1.5 py-0.5 rounded border border-border-strong text-text">
                      {session.status}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Main Debate Stage & Selected Thread */}
          {activeSession && (
            <div className="space-y-4 pt-2">
              {/* Active Debate Header Summary Banner */}
              <div className="p-3.5 rounded bg-surface-deep border border-border-strong relative">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
                  <div className="lg:col-span-5 space-y-1.5">
                    <div className="text-[10px] text-text-muted uppercase tracking-wider flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-accent"></span>
                      RECORDED SESSION
                    </div>
                    <div className="text-sm font-bold text-text-strong flex items-center gap-2">
                      <span>{activeSession.symbol ?? activeSession.id}</span>
                    </div>
                    <div className="text-[11px] text-text-muted">
                      Session: <span className="text-text-strong font-mono">{activeSession.id}</span>
                      {' '}• Side: <span className="text-text-strong">{activeSession.side}</span>
                      {' '}• Status: <span className="text-text-strong">{activeSession.status}</span>
                    </div>
                  </div>

                  <div className="lg:col-span-7 bg-surface-veil p-3 rounded border border-border-subtle space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-text-muted font-semibold flex items-center gap-1">
                        <Scale className="w-3.5 h-3.5 text-accent" />
                        RECORDED CONSENSUS SCORE
                      </span>
                      <span className="text-accent font-bold font-mono-num text-sm">
                        {activeSession.consensusScorePct !== null
                          ? `${activeSession.consensusScorePct.toFixed(1)}%`
                          : "— (not recorded)"}
                      </span>
                    </div>
                    <div className="text-[10px] text-text-subtle">
                      No approval / venue / firewall fields are published for debates — only the
                      recorded turns below.
                    </div>
                  </div>
                </div>
              </div>

              {/* Turn-by-Turn Thread Section Header */}
              <div className="flex items-center justify-between pb-1 border-b border-border-subtle">
                <div className="flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-accent" />
                  <h4 className="text-xs font-bold uppercase tracking-wider text-text-strong">
                    RECORDED DELIBERATION STREAM ({activeSession.turns.length} TURNS)
                  </h4>
                </div>
              </div>

              {/* Chronological Turn-by-Turn Messages */}
              {activeSession.turns.length === 0 ? (
                <div className="p-6 text-center text-text-subtle text-xs">
                  This session recorded no turns.
                </div>
              ) : (
                <div className="space-y-3">
                  {activeSession.turns.map((turn, index) => {
                    const stanceBadge = getStanceBadge(turn.stance);

                    return (
                      <div
                        key={`${activeSession.id}-turn-${index}`}
                        className="p-4 rounded-md border bg-surface-veil border-border-subtle"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-border-subtle">
                          <div className="flex items-center gap-2.5">
                            <div className="w-6 h-6 rounded bg-surface-deep border border-border-strong flex items-center justify-center text-xs font-bold text-accent">
                              {index + 1}
                            </div>
                            <div>
                              <span
                                onClick={() => onInspectAgent && onInspectAgent(turn.agentId)}
                                className="font-bold text-text-strong text-xs hover:text-accent cursor-pointer transition-colors"
                              >
                                {turn.agentId}
                              </span>
                              <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-info-bg text-accent border border-accent ml-2">
                                CONF: {turn.confidencePct !== null ? `${turn.confidencePct}%` : "—"}
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold border flex items-center gap-1 ${stanceBadge.bg} ${stanceBadge.text} ${stanceBadge.border}`}>
                              {stanceBadge.icon}
                              {stanceBadge.label}
                            </span>
                          </div>
                        </div>

                        <div className="my-3 text-xs leading-relaxed text-text-strong">
                          {turn.thesis || <span className="text-text-subtle">— (no thesis recorded)</span>}
                        </div>

                        <div className="pt-2 border-t border-border-subtle flex items-center justify-between text-[9px] text-text-subtle">
                          <span>turn {index + 1} of {activeSession.turns.length}</span>
                          <button
                            onClick={() => handleCopy(turn.thesis, `${activeSession.id}-${index}`)}
                            className="text-text-muted hover:text-accent flex items-center gap-1 font-mono text-[9px]"
                            title="Copy thesis"
                          >
                            {copiedId === `${activeSession.id}-${index}` ? (
                              <Check className="w-2.5 h-2.5 text-positive" />
                            ) : (
                              <Copy className="w-2.5 h-2.5" />
                            )}
                            Copy thesis
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};
