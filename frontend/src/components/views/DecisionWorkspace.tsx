import React, { useState } from 'react';
import { ProvenanceTrace } from '../../types';
import { 
  Network, 
   
  CheckCircle2, 
   
   
  Zap, 
  Scale, 
  
  
  
  Play,
  
  
  BrainCircuit,
  
  
  

} from 'lucide-react';
import { DecisionProvenanceExplorer } from '../DecisionProvenanceExplorer';

interface DecisionWorkspaceProps {
  traces: ProvenanceTrace[];
  onSelectTrace: (traceId: string) => void;
  onDispatchRatifiedOrder?: (orderDesc: string) => void;
}

interface SimulatedDebateStep {
  round: number;
  agent: string;
  role: string;
  avatarColor: string;
  content: string;
  timestamp: string;
  consensusVote: number;
}

export const DecisionWorkspace: React.FC<DecisionWorkspaceProps> = ({
  traces,
  onSelectTrace,
  onDispatchRatifiedOrder,
}) => {
  const [selectedTraceId, setSelectedTraceId] = useState<string>(traces[0]?.executionId || '');
  const [decisionActionStatus, setDecisionActionStatus] = useState<string | null>(null);

  // Live Multi-Agent Debate Simulator State
  const [selectedScenario, setSelectedScenario] = useState<string>('FED_RATE_CUT');
  const [isSimulatingDebate, setIsSimulatingDebate] = useState<boolean>(false);
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(0);
  const [simulatedConsensus, setSimulatedConsensus] = useState<number>(0);
  const [debateFinished, setDebateFinished] = useState<boolean>(false);

  const scenarioPresets = [
    {
      id: 'FED_RATE_CUT',
      title: 'FOMC Unexpected 50bps Rate Cut & Dovish Pivot',
      category: 'MACRO_MONETARY',
      initialThesis: 'Global liquidity expansion favors high-beta duration assets (Crypto & Tech Equities).'
    },
    {
      id: 'SEMI_EARNINGS',
      title: 'Mega-Cap AI Infrastructure Earnings Surge (+35% CapEx)',
      category: 'EQUITY_DISPERSION',
      initialThesis: 'Datacenter chip demand acceleration justifies increasing NVDA/TSM allocation.'
    },
    {
      id: 'GEOPOLITICAL_OIL',
      title: 'Strait of Hormuz Supply Shock (Crude Oil +18%)',
      category: 'TAIL_RISK',
      initialThesis: 'Inflation spike risk necessitates immediate energy hedging and beta trimming.'
    },
    {
      id: 'CRYPTO_INFLOW',
      title: 'Institutional ETF Net Inflows Hit Record $1.8B/Day',
      category: 'MOMENTUM_FLOW',
      initialThesis: 'Severe order-book supply squeeze on BTC/ETH warrants TWAP size acceleration.'
    }
  ];

  const debateSteps: Record<string, SimulatedDebateStep[]> = {
    'FED_RATE_CUT': [
      {
        round: 1,
        agent: 'Macro Regime Agent',
        role: 'Regime Ingestion (Gemini 2.5 Pro)',
        avatarColor: 'text-cyan-400 bg-cyan-950 border-cyan-700',
        content: 'Fed policy rate cut lowers discount rates across risk assets. Real yields plunging 32bps. Recommending +$4.5M allocation to BTC and +$2.8M to NVDA with 1.0x cash leverage.',
        timestamp: '16:42:01.102',
        consensusVote: 94
      },
      {
        round: 2,
        agent: 'Technical Momentum Agent',
        role: 'Market Microstructure (DeepSeek R1)',
        avatarColor: 'text-indigo-400 bg-indigo-950 border-indigo-700',
        content: 'Confirmed breakout above 200-day EMA with expanding spot volume. Order book bid skew is +68% positive across Binance and CME FIX gateways.',
        timestamp: '16:42:01.380',
        consensusVote: 92
      },
      {
        round: 3,
        agent: 'Risk Sentinel & Adversary',
        role: 'Constitutional Governor (Formal SMT)',
        avatarColor: 'text-amber-400 bg-amber-950 border-amber-700',
        content: 'ADVERSARIAL CHALLENGE: Single asset concentration cap for BTC would hit 21.4% (near 25% max). PROPOSAL MODIFICATION: Slice order into 45-minute TWAP and hedge with short-dated delta put option.',
        timestamp: '16:42:01.810',
        consensusVote: 86
      },
      {
        round: 4,
        agent: 'Synthesizer & Supervisor',
        role: 'LangGraph Consensus Arbiter',
        avatarColor: 'text-emerald-400 bg-emerald-950 border-emerald-700',
        content: 'SUPERMAJORITY REACHED (88.5% > 75% threshold). Generated execution packet: Buy $3.8M BTC/USD TWAP (45m window) + Buy $2.2M NVDA VWAP. 15/15 Constitutional firewall rules satisfied.',
        timestamp: '16:42:02.190',
        consensusVote: 88.5
      }
    ],
    'SEMI_EARNINGS': [
      {
        round: 1,
        agent: 'Fundamental Valuation Agent',
        role: 'Corporate 10-Q & Earnings Parser',
        avatarColor: 'text-emerald-400 bg-emerald-950 border-emerald-700',
        content: 'Hyperscaler CapEx guidance revised upward to $210B. NVDA gross margins maintained at 75.2%. Free cash flow multiple compressed to attractive 28x forward.',
        timestamp: '16:42:01.090',
        consensusVote: 91
      },
      {
        round: 2,
        agent: 'Macro Regime Agent',
        role: 'Semiconductor Cycle Model',
        avatarColor: 'text-cyan-400 bg-cyan-950 border-cyan-700',
        content: 'Semiconductor cycle in mid-expansion regime. Supply chain lead times stabilizing at 18 weeks. Supports overweight thesis.',
        timestamp: '16:42:01.320',
        consensusVote: 89
      },
      {
        round: 3,
        agent: 'Risk Sentinel & Adversary',
        role: 'Constitutional Governor',
        avatarColor: 'text-amber-400 bg-amber-950 border-amber-700',
        content: 'ADVERSARIAL CHALLENGE: Cross-asset covariance between NVDA and BTC is 0.64. Increasing both simultaneously increases 99% CVaR tail risk by 0.38%. PROPOSAL: Rebalance funded by trimming defensive short-duration treasuries.',
        timestamp: '16:42:01.710',
        consensusVote: 85
      },
      {
        round: 4,
        agent: 'Synthesizer & Supervisor',
        role: 'Consensus Arbiter',
        avatarColor: 'text-emerald-400 bg-emerald-950 border-emerald-700',
        content: 'CONSENSUS RATIFIED (87.2%). Rebalance approved: Buy $3.5M NVDA via VWAP participation, funded by rotating $3.5M from BIL (US 1-3 Month T-Bills). Zero leverage added.',
        timestamp: '16:42:02.040',
        consensusVote: 87.2
      }
    ],
    'GEOPOLITICAL_OIL': [
      {
        round: 1,
        agent: 'Macro Regime Agent',
        role: 'Commodity & Inflation Tracker',
        avatarColor: 'text-rose-400 bg-rose-950 border-rose-700',
        content: 'Oil shock threatens headline CPI re-acceleration (+40bps). Bond yields spiking across 10Y/30Y curve. Recommend reducing gross risk exposure by 18%.',
        timestamp: '16:42:01.110',
        consensusVote: 95
      },
      {
        round: 2,
        agent: 'Risk Sentinel & Adversary',
        role: 'Constitutional Governor',
        avatarColor: 'text-amber-400 bg-amber-950 border-amber-700',
        content: 'CONSTITUTION §2.1 DE-RISKING PROTOCOL TRIGGERED: Expected Shortfall (CVaR) breached 3.8% tolerance. Mandating 30% reduction in high-beta equity long exposure.',
        timestamp: '16:42:01.450',
        consensusVote: 96
      },
      {
        round: 3,
        agent: 'Technical Momentum Agent',
        role: 'Trend Breakdown Sifter',
        avatarColor: 'text-indigo-400 bg-indigo-950 border-indigo-700',
        content: 'Breakdown below VWAP support on SPY and QQQ. Recommending orderly exit via Iceberg limit orders to minimize market impact.',
        timestamp: '16:42:01.780',
        consensusVote: 92
      },
      {
        round: 4,
        agent: 'Synthesizer & Supervisor',
        role: 'Consensus Arbiter',
        avatarColor: 'text-emerald-400 bg-emerald-950 border-emerald-700',
        content: 'CONSENSUS RATIFIED (94.0%). Emergency de-risking packet: Trim $4.0M SPY and $2.5M high-beta crypto into USD Cash Enclave. Increase cash reserve to 24.5%.',
        timestamp: '16:42:02.120',
        consensusVote: 94.0
      }
    ],
    'CRYPTO_INFLOW': [
      {
        round: 1,
        agent: 'Sentiment & Flow Agent',
        role: 'On-Chain & Exchange Inflow Engine',
        avatarColor: 'text-cyan-400 bg-cyan-950 border-cyan-700',
        content: 'Cumulative net exchange balances down 14,200 BTC in 24h. OTC desks report zero liquid inventory under $65k. Strong positive momentum anomaly.',
        timestamp: '16:42:01.080',
        consensusVote: 96
      },
      {
        round: 2,
        agent: 'Technical Momentum Agent',
        role: 'Microstructure & Liquidity Sifter',
        avatarColor: 'text-indigo-400 bg-indigo-950 border-indigo-700',
        content: 'Order book imbalance 74% bid-side. Low liquidity above current price allows rapid upward re-pricing. Recommending size boost.',
        timestamp: '16:42:01.350',
        consensusVote: 91
      },
      {
        round: 3,
        agent: 'Risk Sentinel & Adversary',
        role: 'Constitutional Governor',
        avatarColor: 'text-amber-400 bg-amber-950 border-amber-700',
        content: 'ADVERSARIAL SCRUTINY: Funding rate at 0.04% per 8h. Mandating cash-only spot purchases on CME Direct and Binance Institutional. No leveraged perps.',
        timestamp: '16:42:01.720',
        consensusVote: 88
      },
      {
        round: 4,
        agent: 'Synthesizer & Supervisor',
        role: 'Consensus Arbiter',
        avatarColor: 'text-emerald-400 bg-emerald-950 border-emerald-700',
        content: 'CONSENSUS RATIFIED (91.5%). Spot Accumulation Approved: Execute $4.2M BTC spot buy across 20-minute TWAP. Slippage cap fixed at 1.2 bps.',
        timestamp: '16:42:02.050',
        consensusVote: 91.5
      }
    ]
  };

  const currentSteps = debateSteps[selectedScenario] || debateSteps['FED_RATE_CUT'];

  const handleStartSimulatedDebate = () => {
    setIsSimulatingDebate(true);
    setCurrentStepIndex(0);
    setDebateFinished(false);
    setSimulatedConsensus(0);

    let step = 0;
    const interval = setInterval(() => {
      step++;
      if (step <= currentSteps.length) {
        setCurrentStepIndex(step);
        setSimulatedConsensus(currentSteps[step - 1].consensusVote);
      } else {
        clearInterval(interval);
        setIsSimulatingDebate(false);
        setDebateFinished(true);
      }
    }, 900);
  };

  const handleAction = (status: string) => {
    setDecisionActionStatus(status);
    if (onDispatchRatifiedOrder) {
      onDispatchRatifiedOrder(status);
    }
    setTimeout(() => setDecisionActionStatus(null), 4000);
  };

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Network className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              INVESTMENT DECISION & PROVENANCE WORKSPACE
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 5 & 6
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Cryptographic Decision Lineage • Adversarial Cross-Examination • Audit Trail Ledger
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">DECISION PROVENANCE:</span>{' '}
            <span className="text-emerald-400 font-bold">100% TRACEABLE</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">HASH ROOT:</span>{' '}
            <span className="text-cyan-300 font-mono text-[11px]">MERKLE BLOCK #4829</span>
          </div>
        </div>
      </div>

      {/* NEW FEATURE: Interactive Live Multi-Agent Debate Simulation & Proposal Generator */}
      <div className="bg-[#0d0f17] border border-cyan-500/30 rounded-md p-4 shadow-2xl space-y-4">
        <div className="flex flex-wrap items-center justify-between pb-3 border-b border-white/[0.06] gap-2">
          <div className="flex items-center gap-2">
            <BrainCircuit className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase text-white tracking-wider">
              LIVE MULTI-AGENT ADVERSARIAL DEBATE SIMULATOR
            </h3>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold">
              LANGGRAPH REASONING
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400 text-[10px]">CONSENSUS GAUGE:</span>
            <div className="w-24 h-2 bg-black/50 rounded-full overflow-hidden border border-white/[0.08]">
              <div 
                className={`h-full transition-all duration-500 ${
                  simulatedConsensus >= 75 ? 'bg-emerald-400' : 'bg-amber-400'
                }`}
                style={{ width: `${simulatedConsensus}%` }}
              />
            </div>
            <span className="text-cyan-300 font-bold font-mono text-[11px]">{simulatedConsensus.toFixed(1)}%</span>
          </div>
        </div>

        {/* Scenario Selection Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          {scenarioPresets.map((sc) => {
            const isSelected = selectedScenario === sc.id;
            return (
              <button
                key={sc.id}
                onClick={() => {
                  setSelectedScenario(sc.id);
                  setCurrentStepIndex(0);
                  setDebateFinished(false);
                  setSimulatedConsensus(0);
                }}
                className={`p-2.5 rounded text-left transition-all border ${
                  isSelected
                    ? 'bg-cyan-950/60 border-cyan-500 text-white shadow-[0_0_12px_rgba(0,240,255,0.15)]'
                    : 'bg-white/[0.02] border-white/[0.06] text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                }`}
              >
                <div className="text-[9px] font-bold text-cyan-400 uppercase tracking-wider mb-1">
                  {sc.category}
                </div>
                <div className="text-xs font-semibold text-slate-200 leading-snug line-clamp-2">
                  {sc.title}
                </div>
              </button>
            );
          })}
        </div>

        {/* Run Debate Button */}
        <div className="flex items-center justify-between pt-1">
          <div className="text-xs text-slate-400">
            Simulate 4 rounds of LangGraph cross-examination, SMT risk veto checking, and supermajority voting.
          </div>
          <button
            onClick={handleStartSimulatedDebate}
            disabled={isSimulatingDebate}
            className={`px-4 py-1.5 rounded font-bold text-xs flex items-center gap-1.5 transition-all ${
              isSimulatingDebate
                ? 'bg-cyan-950 text-cyan-400 border border-cyan-800 animate-pulse cursor-not-allowed'
                : 'bg-cyan-500 hover:bg-cyan-400 text-black shadow-[0_0_12px_rgba(0,240,255,0.3)]'
            }`}
          >
            {isSimulatingDebate ? (
              <>
                <BrainCircuit className="w-3.5 h-3.5 animate-spin" />
                <span>AGENTS DEBATING (ROUND {currentStepIndex}/4)...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                <span>RUN ADVERSARIAL DEBATE</span>
              </>
            )}
          </button>
        </div>

        {/* Live Debate Timeline Feed */}
        <div className="space-y-2.5 pt-2 border-t border-white/[0.06]">
          {currentStepIndex === 0 && !debateFinished && (
            <div className="p-6 text-center text-slate-500 text-xs rounded bg-black/20 border border-dashed border-white/[0.08]">
              Select a market scenario above and click <strong className="text-cyan-400">RUN ADVERSARIAL DEBATE</strong> to trigger the live LangGraph consensus pipeline.
            </div>
          )}

          {currentSteps.slice(0, currentStepIndex).map((step, idx) => (
            <div 
              key={idx}
              className="p-3 rounded bg-black/40 border border-white/[0.08] space-y-1.5 animate-fade-in"
            >
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${step.avatarColor}`}>
                    ROUND {step.round} • {step.agent}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">({step.role})</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-emerald-400 font-mono">Vote: {step.consensusVote}%</span>
                  <span className="text-[10px] text-slate-500 font-mono">{step.timestamp}</span>
                </div>
              </div>
              <p className="text-xs text-slate-200 pl-1 leading-relaxed">
                {step.content}
              </p>
            </div>
          ))}

          {/* Synthesized Proposal Authorization Card when Finished */}
          {debateFinished && (
            <div className="p-4 rounded bg-cyan-950/30 border border-cyan-500/50 space-y-3 animate-fade-in">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-cyan-400" />
                  <span className="font-bold text-xs text-white uppercase tracking-wider">
                    SYNTHESIZED ACTIONABLE REBALANCE PACKET RATIFIED
                  </span>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">
                  SUPERMAJORITY {simulatedConsensus.toFixed(1)}%
                </span>
              </div>
              <p className="text-xs text-slate-300">
                The agent ensemble completed 4 debate rounds. SMT Risk Sentinel verified 0 constitutional limit violations.
              </p>
              <div className="flex items-center justify-end gap-3 pt-1 border-t border-cyan-500/20">
                <button
                  onClick={() => {
                    setDebateFinished(false);
                    setCurrentStepIndex(0);
                  }}
                  className="px-3 py-1.5 rounded bg-white/[0.04] text-xs text-slate-400 hover:text-white"
                >
                  DISMISS
                </button>
                <button
                  onClick={() => handleAction(`Simulated proposal for ${selectedScenario} ratified and routed to SOR slicer!`)}
                  className="px-4 py-1.5 rounded bg-cyan-500 hover:bg-cyan-400 text-black font-bold text-xs flex items-center gap-1.5 shadow-[0_0_12px_rgba(0,240,255,0.4)]"
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>AUTHORIZE &amp; EXECUTE SLICES</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Primary Provenance Lineage Explorer */}
      <DecisionProvenanceExplorer
        traces={traces}
        selectedTraceId={selectedTraceId}
        onSelectTrace={(id) => {
          setSelectedTraceId(id);
          onSelectTrace(id);
        }}
      />

      {/* Pending Gated Decision Queue */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Scale className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold uppercase text-white tracking-wider">
              PENDING GATED PROPOSALS REQUIRING SUPERVISION
            </h3>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold">
              1 PENDING SIGN-OFF
            </span>
          </div>
          <span className="text-[10px] text-slate-400">AUTONOMY: SUPERVISED</span>
        </div>

        {decisionActionStatus ? (
          <div className="p-4 my-3 rounded bg-emerald-950/40 border border-emerald-700/60 text-emerald-300 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>{decisionActionStatus}</span>
            </div>
            <span className="text-[10px] font-mono">MERKLE LEAF #9a204c</span>
          </div>
        ) : (
          <div className="my-3 p-3.5 rounded bg-white/[0.02] border border-white/[0.06] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                  BUY $3.2M BTC/USD
                </span>
                <span className="text-xs text-white font-semibold">
                  Breakout Momentum Allocation (TWAP Slicer)
                </span>
              </div>
              <span className="text-[10px] text-slate-400 font-mono">TIMESTAMP: 16:15:00 UTC</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div className="p-2.5 rounded bg-black/30 border border-white/[0.04]">
                <div className="text-[9px] text-slate-500 uppercase">PROPOSING AGENTS</div>
                <div className="text-xs font-semibold text-slate-200 mt-1">Macro Regime + Technical Momentum</div>
                <div className="text-[10px] text-cyan-300 mt-0.5">Consensus: 87.4%</div>
              </div>

              <div className="p-2.5 rounded bg-black/30 border border-white/[0.04]">
                <div className="text-[9px] text-slate-500 uppercase">ADVERSARIAL CHALLENGE</div>
                <div className="text-xs font-semibold text-rose-300 mt-1">Funding rate premium elevated</div>
                <div className="text-[10px] text-slate-400 mt-0.5">Mitigated by 50% TWAP duration extension</div>
              </div>

              <div className="p-2.5 rounded bg-black/30 border border-white/[0.04]">
                <div className="text-[9px] text-slate-500 uppercase">RISK FIREWALL CHECK</div>
                <div className="text-xs font-semibold text-emerald-400 mt-1">15/15 CHECKS PASSED</div>
                <div className="text-[10px] text-slate-400 mt-0.5">Post-trade DD margin: 2.16% remaining</div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center justify-end gap-3 pt-2 border-t border-white/[0.05]">
              <button
                onClick={() => handleAction('Proposal rejected by institutional supervisor. Reason logged to Merkle audit chain.')}
                className="px-3 py-1.5 rounded bg-white/[0.04] hover:bg-white/[0.08] text-xs text-slate-400 hover:text-white transition-colors"
              >
                REJECT PROPOSAL
              </button>

              <button
                onClick={() => handleAction('Proposal ratified & authorized! Order dispatched to TWAP execution router.')}
                className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-xs text-black font-bold font-mono transition-all shadow-[0_0_12px_rgba(0,240,255,0.4)] flex items-center gap-1.5"
              >
                <Zap className="w-3.5 h-3.5" />
                <span>RATIFY &amp; DISPATCH ORDER</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
