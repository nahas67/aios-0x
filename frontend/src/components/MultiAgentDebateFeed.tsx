import React, { useState, useEffect } from 'react';
import { 
  DebateSession, 
   
   
  AssetClass 
} from '../types';
import { INITIAL_DEBATE_SESSIONS } from '../data/mockDebates';
import { 
  BrainCircuit, 
  Scale, 
  ShieldCheck, 
  AlertTriangle, 
  CheckCircle2, 
  MessageSquare, 
   
  TrendingUp, 
  TrendingDown, 
  Sliders, 
  Hash, 
  Copy, 
  Check, 
  Play, 
  Pause, 
  RotateCcw, 
  Sparkles, 
  Filter, 
  Search, 
  

  FileText,






} from 'lucide-react';

interface MultiAgentDebateFeedProps {
  className?: string;
  onInspectAgent?: (agentId: string) => void;
}

export const MultiAgentDebateFeed: React.FC<MultiAgentDebateFeedProps> = ({
  className = '',
  onInspectAgent
}) => {
  const [sessions] = useState<DebateSession[]>(INITIAL_DEBATE_SESSIONS);
  const [selectedSessionId, setSelectedSessionId] = useState<string>(INITIAL_DEBATE_SESSIONS[0]?.id || '');
  const [selectedAssetFilter, setSelectedAssetFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  
  // Live simulation state
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simulatedTurnIndex, setSimulatedTurnIndex] = useState<number | null>(null);
  const [activeSimulationSessionId, setActiveSimulationSessionId] = useState<string | null>(null);

  const activeSession = sessions.find(s => s.id === selectedSessionId) || sessions[0];

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(id);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  // Filtered list of sessions
  const filteredSessions = sessions.filter(session => {
    const matchesAsset = selectedAssetFilter === 'ALL' || session.assetClass === selectedAssetFilter;
    const matchesSearch = searchQuery === '' || 
      session.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      session.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      session.proposingAgent.toLowerCase().includes(searchQuery.toLowerCase()) ||
      session.resolution.summary.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesAsset && matchesSearch;
  });

  // Simulated live debate turn progression
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (isSimulating && activeSession && simulatedTurnIndex !== null) {
      if (simulatedTurnIndex < activeSession.turns.length - 1) {
        timer = setTimeout(() => {
          setSimulatedTurnIndex(prev => (prev !== null ? prev + 1 : 0));
        }, 3200);
      } else {
        setIsSimulating(false);
      }
    }
    return () => clearTimeout(timer);
  }, [isSimulating, simulatedTurnIndex, activeSession]);

  const handleStartLiveSimulation = () => {
    setSimulatedTurnIndex(0);
    setIsSimulating(true);
    setActiveSimulationSessionId(activeSession.id);
  };

  const handleResetSimulation = () => {
    setIsSimulating(false);
    setSimulatedTurnIndex(null);
    setActiveSimulationSessionId(null);
  };

  // Helper for stance formatting
  const getStanceBadge = (stance: string) => {
    switch (stance) {
      case 'PROPOSE_LONG':
        return {
          label: 'PROPOSAL • LONG',
          bg: 'bg-emerald-950/60',
          text: 'text-emerald-300',
          border: 'border-emerald-700/60',
          icon: <TrendingUp className="w-3 h-3 text-emerald-400" />
        };
      case 'PROPOSE_SHORT':
        return {
          label: 'PROPOSAL • SHORT HEDGE',
          bg: 'bg-rose-950/60',
          text: 'text-rose-300',
          border: 'border-rose-700/60',
          icon: <TrendingDown className="w-3 h-3 text-rose-400" />
        };
      case 'CHALLENGE_RISK':
      case 'CHALLENGE_VALUATION':
        return {
          label: 'ADVERSARIAL CHALLENGE',
          bg: 'bg-amber-950/60',
          text: 'text-amber-300',
          border: 'border-amber-700/60',
          icon: <AlertTriangle className="w-3 h-3 text-amber-400" />
        };
      case 'REBUTTAL':
        return {
          label: 'QUANTITATIVE REBUTTAL',
          bg: 'bg-cyan-950/60',
          text: 'text-cyan-300',
          border: 'border-cyan-700/60',
          icon: <Scale className="w-3 h-3 text-cyan-400" />
        };
      case 'FIREWALL_VERIFICATION':
        return {
          label: 'RISK FIREWALL AUDIT',
          bg: 'bg-purple-950/60',
          text: 'text-purple-300',
          border: 'border-purple-700/60',
          icon: <ShieldCheck className="w-3 h-3 text-purple-400" />
        };
      case 'SUPERMAJORITY_SYNTHESIS':
        return {
          label: 'SUPERMAJORITY CONSENSUS',
          bg: 'bg-emerald-950/80',
          text: 'text-emerald-200',
          border: 'border-emerald-500',
          icon: <CheckCircle2 className="w-3 h-3 text-emerald-400" />
        };
      default:
        return {
          label: stance,
          bg: 'bg-white/[0.04]',
          text: 'text-slate-300',
          border: 'border-white/[0.08]',
          icon: <BrainCircuit className="w-3 h-3 text-cyan-400" />
        };
    }
  };

  const getAssetBadge = (assetClass: AssetClass) => {
    switch (assetClass) {
      case 'POLYMARKET':
        return { label: 'POLYMARKET PREDICTION', color: 'text-pink-400 border-pink-800 bg-pink-950/40' };
      case 'GLOBAL_EQUITY':
        return { label: 'GLOBAL EQUITY (INTL)', color: 'text-blue-400 border-blue-800 bg-blue-950/40' };
      case 'COMMODITY':
        return { label: 'PHYSICAL COMMODITY', color: 'text-amber-400 border-amber-800 bg-amber-950/40' };
      case 'FX':
        return { label: 'FOREX / G10 & EM', color: 'text-indigo-400 border-indigo-800 bg-indigo-950/40' };
      case 'US_EQUITY':
        return { label: 'US EQUITY', color: 'text-cyan-400 border-cyan-800 bg-cyan-950/40' };
      case 'CRYPTO':
        return { label: 'CRYPTO / DIGITAL', color: 'text-violet-400 border-violet-800 bg-violet-950/40' };
      case 'RATES':
        return { label: 'RATES & SOVEREIGN', color: 'text-teal-400 border-teal-800 bg-teal-950/40' };
      default:
        return { label: assetClass, color: 'text-slate-400 border-slate-700 bg-slate-900' };
    }
  };

  // Visible turns based on simulation or full view
  const visibleTurns = (activeSimulationSessionId === activeSession?.id && simulatedTurnIndex !== null)
    ? activeSession.turns.slice(0, simulatedTurnIndex + 1)
    : activeSession?.turns || [];

  const currentConsensusPct = (activeSimulationSessionId === activeSession?.id && simulatedTurnIndex !== null)
    ? Math.min(100, Math.round((simulatedTurnIndex + 1) / activeSession.turns.length * activeSession.consensusScorePct))
    : activeSession?.consensusScorePct || 0;

  return (
    <div className={`bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl space-y-4 font-mono ${className}`}>
      {/* Top Header & Overview */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded bg-cyan-950/60 border border-cyan-700/60 text-cyan-400">
              <BrainCircuit className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
                  MULTI-AGENT DEBATE &amp; ADVERSARIAL CONSENSUS FEED
                </h3>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center gap-1 font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  GATED SYNTHESIS PIPELINE
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Real-time multi-agent discourse stream • Turn-by-turn evidentiary support • Cryptographically proven resolution
              </p>
            </div>
          </div>
        </div>

        {/* Live Simulation & Action Controls */}
        <div className="flex items-center gap-2">
          {activeSimulationSessionId === activeSession?.id && isSimulating ? (
            <button
              onClick={() => setIsSimulating(false)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-amber-950/70 border border-amber-700 text-amber-300 text-xs font-semibold hover:bg-amber-900 transition-colors"
            >
              <Pause className="w-3.5 h-3.5" /> PAUSE STREAM
            </button>
          ) : (
            <button
              onClick={handleStartLiveSimulation}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-cyan-950/70 border border-cyan-600 text-cyan-300 text-xs font-semibold hover:bg-cyan-900 transition-colors shadow-[0_0_12px_rgba(0,240,255,0.15)]"
            >
              <Play className="w-3.5 h-3.5 fill-current" /> SIMULATE LIVE REPLAY
            </button>
          )}

          {activeSimulationSessionId === activeSession?.id && simulatedTurnIndex !== null && (
            <button
              onClick={handleResetSimulation}
              className="p-1.5 rounded bg-white/[0.04] border border-white/[0.08] text-slate-400 hover:text-white transition-colors"
              title="Reset Simulation"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          )}

          <div className="h-6 w-px bg-white/[0.08]" />

          <div className="text-xs text-slate-400 flex items-center gap-1.5">
            <span>DEBATE SESSIONS:</span>
            <span className="text-cyan-300 font-bold font-mono-num">{sessions.length} ACTIVE</span>
          </div>
        </div>
      </div>

      {/* Asset Class Filter Bar & Search */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-black/40 p-2 rounded border border-white/[0.06]">
        {/* Asset Class Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] text-slate-500 uppercase mr-1 flex items-center gap-1">
            <Filter className="w-3 h-3 text-slate-500" /> CLASS:
          </span>
          {['ALL', 'POLYMARKET', 'GLOBAL_EQUITY', 'COMMODITY', 'FX', 'US_EQUITY'].map((cls) => (
            <button
              key={cls}
              onClick={() => setSelectedAssetFilter(cls)}
              className={`px-2 py-1 text-[10px] rounded font-semibold transition-all ${
                selectedAssetFilter === cls
                  ? 'bg-cyan-950 text-cyan-300 border border-cyan-700 shadow-sm'
                  : 'bg-white/[0.02] text-slate-400 hover:text-slate-200 border border-white/[0.04]'
              }`}
            >
              {cls === 'GLOBAL_EQUITY' ? 'GLOBAL INTL' : cls}
            </button>
          ))}
        </div>

        {/* Search Box */}
        <div className="relative min-w-[220px]">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search debate thesis, symbol..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-black/60 border border-white/[0.08] rounded pl-8 pr-3 py-1 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono"
          />
        </div>
      </div>

      {/* Debate Session Selection Cards (Horizontal Scroller / Grid) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {filteredSessions.map((session) => {
          const isSelected = session.id === activeSession?.id;
          const assetBadge = getAssetBadge(session.assetClass);
          const isShort = session.side === 'SHORT' || session.side === 'HEDGE';

          return (
            <div
              key={session.id}
              onClick={() => {
                setSelectedSessionId(session.id);
                handleResetSimulation();
              }}
              className={`p-3 rounded border transition-all cursor-pointer relative overflow-hidden ${
                isSelected
                  ? 'bg-white/[0.06] border-cyan-500/80 shadow-[0_0_15px_rgba(0,240,255,0.12)]'
                  : 'bg-white/[0.02] hover:bg-white/[0.04] border-white/[0.06] hover:border-white/[0.15]'
              }`}
            >
              {/* Active selection accent line */}
              {isSelected && (
                <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-cyan-500 via-emerald-400 to-cyan-500" />
              )}

              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold text-white tracking-wide">{session.symbol}</span>
                    <span className={`text-[9px] px-1 py-0.2 rounded border font-semibold ${
                      isShort ? 'bg-rose-950/60 text-rose-300 border-rose-800' : 'bg-emerald-950/60 text-emerald-300 border-emerald-800'
                    }`}>
                      {session.side}
                    </span>
                    <span className={`text-[8px] px-1 py-0.2 rounded border font-medium ${assetBadge.color}`}>
                      {session.assetClass}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-300 font-medium line-clamp-1 mt-0.5">
                    {session.name}
                  </div>
                </div>

                <div className="text-right">
                  <span className="text-xs font-bold text-cyan-300 font-mono-num">
                    {session.consensusScorePct.toFixed(1)}%
                  </span>
                  <div className="text-[9px] text-slate-400 font-normal">CONSENSUS</div>
                </div>
              </div>

              {/* Middle Metrics: Sizing & Participants */}
              <div className="mt-2.5 pt-2 border-t border-white/[0.04] flex items-center justify-between text-[10px] text-slate-400">
                <div>
                  <span>APPROVED: </span>
                  <span className="text-white font-semibold font-mono-num">
                    ${(session.resolution.finalApprovedNotionalUsd / 1000000).toFixed(2)}M
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span>{session.roundsCount} ROUNDS</span>
                  <span>•</span>
                  <span>{session.participantsCount} AGENTS</span>
                </div>
              </div>

              {/* Status Badge & Timestamp */}
              <div className="mt-2 flex items-center justify-between text-[9px]">
                <span className={`px-1.5 py-0.5 rounded font-semibold border ${
                  session.status === 'RESOLVED_APPROVED'
                    ? 'bg-emerald-950/50 text-emerald-300 border-emerald-700/60'
                    : session.status === 'RESOLVED_HAIRCUT'
                    ? 'bg-amber-950/50 text-amber-300 border-amber-700/60'
                    : 'bg-rose-950/50 text-rose-300 border-rose-700/60'
                }`}>
                  {session.status === 'RESOLVED_HAIRCUT' ? 'APPROVED (SIZED-DOWN)' : session.status.replace('_', ' ')}
                </span>
                <span className="text-slate-500 font-mono">{session.initiatedAt.split(' ')[1]} UTC</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Main Debate Stage & Selected Thread */}
      {activeSession && (
        <div className="space-y-4 pt-2">
          {/* Active Debate Header Summary Banner */}
          <div className="p-3.5 rounded bg-black/60 border border-white/[0.08] relative">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
              {/* Left Column: Trade Details */}
              <div className="lg:col-span-4 space-y-1.5">
                <div className="text-[10px] text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
                  DELIBERATION TARGET &amp; PROPOSAL
                </div>
                <div className="text-sm font-bold text-white flex items-center gap-2">
                  <span>{activeSession.name}</span>
                  <span className="text-xs text-cyan-300 font-mono">({activeSession.symbol})</span>
                </div>
                <div className="text-xs text-slate-400">
                  <span>Initiated by: </span>
                  <span className="text-slate-200 font-semibold">{activeSession.proposingAgent}</span>
                </div>
                <div className="text-[11px] text-slate-400 flex items-center gap-3 pt-1">
                  <div>
                    PROPOSED NOTIONAL:{' '}
                    <span className="text-slate-200 font-mono-num font-semibold">
                      ${(activeSession.proposedNotionalUsd / 1000000).toFixed(2)}M
                    </span>
                  </div>
                  <div>
                    APPROVED:{' '}
                    <span className="text-emerald-400 font-mono-num font-bold">
                      ${(activeSession.resolution.finalApprovedNotionalUsd / 1000000).toFixed(2)}M
                    </span>
                  </div>
                </div>
              </div>

              {/* Center Column: Gated Consensus Progress Gauge */}
              <div className="lg:col-span-5 bg-white/[0.02] p-3 rounded border border-white/[0.06] space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400 font-semibold flex items-center gap-1">
                    <Scale className="w-3.5 h-3.5 text-cyan-400" />
                    REPUTATION-WEIGHTED CONSENSUS SCORE
                  </span>
                  <span className="text-cyan-300 font-bold font-mono-num text-sm">
                    {currentConsensusPct.toFixed(1)}%
                  </span>
                </div>

                {/* Progress Bar with 75% Supermajority threshold marker */}
                <div className="relative w-full h-3 bg-black/60 rounded-full overflow-hidden border border-white/[0.08]">
                  <div 
                    className="h-full bg-gradient-to-r from-cyan-500 via-teal-400 to-emerald-400 transition-all duration-700"
                    style={{ width: `${currentConsensusPct}%` }}
                  />
                  {/* 75% Threshold Marker Line */}
                  <div 
                    className="absolute top-0 bottom-0 w-0.5 bg-amber-400 shadow-[0_0_8px_#f59e0b]"
                    style={{ left: '75%' }}
                    title="75.0% Required Supermajority Threshold"
                  />
                </div>

                <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>THRESHOLD: <strong className="text-amber-400">75.0% SUPERMAJORITY</strong></span>
                  <span className="text-emerald-400 font-semibold">
                    {currentConsensusPct >= 75 ? '✓ QUORUM & THRESHOLD ACHIEVED' : 'DELIBERATING...'}
                  </span>
                </div>
              </div>

              {/* Right Column: Execution Firewall State */}
              <div className="lg:col-span-3 bg-white/[0.02] p-3 rounded border border-white/[0.06] space-y-1.5 text-xs">
                <div className="text-[10px] text-slate-400 uppercase tracking-wider flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  GOVERNANCE &amp; FIREWALL
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">RISK FIREWALL:</span>
                  <span className="text-emerald-400 font-bold">15/15 CHECKS PASSED</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">ROUTING VENUE:</span>
                  <span className="text-slate-200 truncate max-w-[130px]" title={activeSession.resolution.approvedParameters.venue}>
                    {activeSession.resolution.approvedParameters.venue}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">AUDIT ANCHOR:</span>
                  <span className="text-cyan-300 font-mono text-[10px]">SHA-256 SECURED</span>
                </div>
              </div>
            </div>
          </div>

          {/* Turn-by-Turn Thread Section Header */}
          <div className="flex items-center justify-between pb-1 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-cyan-400" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                STRUCTURED DELIBERATION STREAM ({visibleTurns.length} OF {activeSession.turns.length} TURNS)
              </h4>
            </div>
            {isSimulating && (
              <span className="text-[10px] text-cyan-400 flex items-center gap-1.5 animate-pulse">
                <Sparkles className="w-3 h-3" /> STREAMING TURN {simulatedTurnIndex !== null ? simulatedTurnIndex + 1 : 1}...
              </span>
            )}
          </div>

          {/* Chronological Turn-by-Turn Messages */}
          <div className="space-y-3">
            {visibleTurns.map((turn, index) => {
              const stanceBadge = getStanceBadge(turn.stance);
              const isLatestTurn = index === visibleTurns.length - 1;

              return (
                <div
                  key={turn.id}
                  className={`p-4 rounded-md border transition-all ${
                    turn.stance === 'SUPERMAJORITY_SYNTHESIS'
                      ? 'bg-emerald-950/20 border-emerald-600/60 shadow-[0_0_15px_rgba(16,185,129,0.1)]'
                      : turn.stance === 'CHALLENGE_RISK' || turn.stance === 'CHALLENGE_VALUATION'
                      ? 'bg-amber-950/15 border-amber-700/50'
                      : 'bg-white/[0.02] border-white/[0.06]'
                  } ${isLatestTurn && isSimulating ? 'ring-1 ring-cyan-500/50' : ''}`}
                >
                  {/* Speaker Header */}
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-white/[0.04]">
                    <div className="flex items-center gap-2.5">
                      <div className="w-6 h-6 rounded bg-black/60 border border-white/[0.1] flex items-center justify-center text-xs font-bold text-cyan-300">
                        {turn.turnNumber}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span 
                            onClick={() => onInspectAgent && onInspectAgent(turn.agentId)}
                            className="font-bold text-white text-xs hover:text-cyan-300 cursor-pointer transition-colors"
                          >
                            {turn.agentName}
                          </span>
                          <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-black/50 text-slate-300 border border-white/[0.08]">
                            {turn.modelVersion}
                          </span>
                          <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                            R: {turn.reputationScore.toFixed(2)}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Stance Pill & Turn Time */}
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold border flex items-center gap-1 ${stanceBadge.bg} ${stanceBadge.text} ${stanceBadge.border}`}>
                        {stanceBadge.icon}
                        {stanceBadge.label}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">{turn.timestamp}</span>
                    </div>
                  </div>

                  {/* Core Argument / Analytical Thesis */}
                  <div className="my-3 text-xs leading-relaxed text-slate-200">
                    {turn.thesis}
                  </div>

                  {/* Structured Evidentiary Support Grid */}
                  {turn.evidence && turn.evidence.length > 0 && (
                    <div className="mt-3 pt-2.5 border-t border-white/[0.04] space-y-2">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <FileText className="w-3 h-3 text-cyan-400" />
                        EVIDENTIARY DATA ARTIFACTS &amp; INDEPENDENT AUDIT
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                        {turn.evidence.map((item) => (
                          <div
                            key={item.id}
                            className="p-2.5 rounded bg-black/40 border border-white/[0.06] text-[11px] space-y-1.5 flex flex-col justify-between"
                          >
                            <div>
                              <div className="flex items-center justify-between text-[9px] text-slate-400">
                                <span className="px-1 py-0.2 rounded bg-white/[0.04] text-cyan-300 border border-white/[0.06] font-semibold">
                                  {item.dataType}
                                </span>
                                <span className="text-emerald-400 flex items-center gap-0.5">
                                  <CheckCircle2 className="w-2.5 h-2.5" /> VERIFIED
                                </span>
                              </div>
                              <div className="font-semibold text-slate-100 mt-1 line-clamp-1">
                                {item.claim}
                              </div>
                              <div className="text-[10px] text-slate-300 mt-0.5 font-normal">
                                {item.metricValue}
                              </div>
                            </div>

                            <div className="pt-1.5 border-t border-white/[0.04] flex items-center justify-between text-[9px] text-slate-400">
                              <span className="truncate max-w-[140px]" title={item.source}>
                                Source: {item.source}
                              </span>
                              {item.verificationHash && (
                                <button
                                  onClick={() => handleCopy(item.verificationHash || '', item.id)}
                                  className="text-slate-400 hover:text-cyan-300 flex items-center gap-1 font-mono text-[8px]"
                                  title="Copy Verification Hash"
                                >
                                  {copiedHash === item.id ? (
                                    <Check className="w-2.5 h-2.5 text-emerald-400" />
                                  ) : (
                                    <Copy className="w-2.5 h-2.5" />
                                  )}
                                  {item.verificationHash.slice(0, 6)}...
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Counter-Arguments Addressed (if present) */}
                  {turn.counterArgumentsAddressed && turn.counterArgumentsAddressed.length > 0 && (
                    <div className="mt-2.5 p-2 rounded bg-cyan-950/20 border border-cyan-800/40 text-[11px] space-y-1">
                      <div className="text-[9px] font-bold uppercase text-cyan-300 flex items-center gap-1">
                        <Check className="w-3 h-3 text-cyan-400" /> REBUTTAL RESOLUTIONS ADDRESSED:
                      </div>
                      <ul className="list-disc list-inside text-slate-300 text-[10px] space-y-0.5">
                        {turn.counterArgumentsAddressed.map((arg, i) => (
                          <li key={i}>{arg}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Suggested Risk Adjustments (if present) */}
                  {turn.suggestedRiskAdjustment && (
                    <div className="mt-2.5 p-2 rounded bg-amber-950/20 border border-amber-800/40 text-[11px] flex flex-wrap items-center gap-3">
                      <div className="text-[9px] font-bold uppercase text-amber-300 flex items-center gap-1">
                        <Sliders className="w-3 h-3 text-amber-400" /> MANDATED RISK ADJUSTMENTS:
                      </div>
                      {turn.suggestedRiskAdjustment.sizingAdjustmentPct && (
                        <span className="text-rose-300 font-semibold">
                          Sizing Haircut: {turn.suggestedRiskAdjustment.sizingAdjustmentPct}%
                        </span>
                      )}
                      {turn.suggestedRiskAdjustment.maxNotionalUsd && (
                        <span className="text-slate-200">
                          Max Cap: ${(turn.suggestedRiskAdjustment.maxNotionalUsd / 1000000).toFixed(2)}M
                        </span>
                      )}
                      {turn.suggestedRiskAdjustment.stopLossPrice && (
                        <span className="text-rose-400 font-semibold">
                          Stop-Loss: ${turn.suggestedRiskAdjustment.stopLossPrice}
                        </span>
                      )}
                      {turn.suggestedRiskAdjustment.executionMethod && (
                        <span className="text-cyan-300">
                          Route: {turn.suggestedRiskAdjustment.executionMethod}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Final Resolution Card */}
          {(!isSimulating || simulatedTurnIndex === activeSession.turns.length - 1) && (
            <div className="p-4 rounded-md bg-gradient-to-br from-emerald-950/30 via-black to-cyan-950/30 border border-emerald-600/60 shadow-2xl space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-emerald-800/40">
                <div className="flex items-center gap-2">
                  <div className="p-1 rounded bg-emerald-900/60 border border-emerald-600 text-emerald-300">
                    <CheckCircle2 className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold tracking-wider text-emerald-200 uppercase">
                      FINAL RESOLUTION &amp; GATED CONSENSUS EXECUTION OUTCOME
                    </h4>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Resolved in {activeSession.roundsCount} debate rounds • {activeSession.consensusScorePct}% Consensus Supermajority
                    </span>
                  </div>
                </div>

                <span className="px-2.5 py-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-500 font-bold text-xs">
                  {activeSession.resolution.outcomeStatus.replace(/_/g, ' ')}
                </span>
              </div>

              {/* Summary Text */}
              <div className="text-xs text-slate-200 leading-relaxed">
                <strong className="text-emerald-300 font-semibold">Consensus Verdict: </strong>
                {activeSession.resolution.summary}
              </div>

              {/* Key Compromise */}
              <div className="p-2.5 rounded bg-black/40 border border-white/[0.06] text-xs text-slate-300">
                <div className="text-[10px] text-amber-400 font-bold uppercase tracking-wider mb-0.5">
                  KEY COMPROMISE &amp; ADVERSARIAL RECONCILIATION
                </div>
                {activeSession.resolution.keyCompromise}
              </div>

              {/* Approved Execution Parameters Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 pt-1 text-center">
                <div className="p-2 rounded bg-black/50 border border-white/[0.04]">
                  <div className="text-[9px] text-slate-400 uppercase">SYMBOL</div>
                  <div className="text-xs font-bold text-white">{activeSession.resolution.approvedParameters.symbol}</div>
                </div>
                <div className="p-2 rounded bg-black/50 border border-white/[0.04]">
                  <div className="text-[9px] text-slate-400 uppercase">APPROVED SIZE</div>
                  <div className="text-xs font-bold text-emerald-400 font-mono-num">
                    {activeSession.resolution.approvedParameters.size.toLocaleString()}
                  </div>
                </div>
                <div className="p-2 rounded bg-black/50 border border-white/[0.04]">
                  <div className="text-[9px] text-slate-400 uppercase">TARGET FILL</div>
                  <div className="text-xs font-bold text-slate-200 font-mono-num">
                    ${activeSession.resolution.approvedParameters.fillPriceTarget.toLocaleString()}
                  </div>
                </div>
                <div className="p-2 rounded bg-black/50 border border-white/[0.04]">
                  <div className="text-[9px] text-slate-400 uppercase">STOP-LOSS TRIGGER</div>
                  <div className="text-xs font-bold text-rose-400 font-mono-num">
                    ${activeSession.resolution.approvedParameters.stopLoss.toLocaleString()}
                  </div>
                </div>
                <div className="p-2 rounded bg-black/50 border border-white/[0.04]">
                  <div className="text-[9px] text-slate-400 uppercase">TAKE PROFIT</div>
                  <div className="text-xs font-bold text-emerald-400 font-mono-num">
                    ${activeSession.resolution.approvedParameters.takeProfit.toLocaleString()}
                  </div>
                </div>
                <div className="p-2 rounded bg-black/50 border border-white/[0.04]">
                  <div className="text-[9px] text-slate-400 uppercase">EXECUTION VENUE</div>
                  <div className="text-xs font-bold text-cyan-300 truncate" title={activeSession.resolution.approvedParameters.venue}>
                    {activeSession.resolution.approvedParameters.venue}
                  </div>
                </div>
                <div className="p-2 rounded bg-black/50 border border-white/[0.04]">
                  <div className="text-[9px] text-slate-400 uppercase">FIREWALL CHECK</div>
                  <div className="text-xs font-bold text-emerald-400">
                    {activeSession.resolution.approvedParameters.riskFirewallPassed}/{activeSession.resolution.approvedParameters.riskFirewallTotal} PASS
                  </div>
                </div>
              </div>

              {/* Merkle Proof Footer */}
              <div className="pt-2 border-t border-white/[0.06] flex flex-wrap items-center justify-between text-[10px] text-slate-400 font-mono">
                <div className="flex items-center gap-2 truncate max-w-full">
                  <Hash className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                  <span className="text-slate-500">MERKLE STATE DIGEST:</span>
                  <span className="text-slate-300 truncate select-all">{activeSession.resolution.merkleProofDigest}</span>
                </div>
                <button
                  onClick={() => handleCopy(activeSession.resolution.merkleProofDigest, 'resolution-digest')}
                  className="text-cyan-400 hover:text-cyan-200 flex items-center gap-1 shrink-0"
                >
                  {copiedHash === 'resolution-digest' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  Copy Merkle Proof
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
