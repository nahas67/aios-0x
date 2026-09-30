import React, { useState } from 'react';
import { AgentNode } from '../../types';
import {
  Users2,
  Award,
} from 'lucide-react';
import { AgentNetworkVisualizer } from '../AgentNetworkVisualizer';
import { MultiAgentDebateFeed } from '../MultiAgentDebateFeed';
import { intelligenceApi } from '../../api/backend';
import { useApi } from '../../hooks/useApi';
import { adaptAgents } from '../../adapters/agents';
import { Unavailable } from '../Unavailable';

interface AgentNetworkWorkspaceProps {
  onSelectAgent: (agent: AgentNode) => void;
}

/**
 * Agents workspace wired to GET /api/v1/agents.
 * (Debate feed untouched — it needs the A1 debates endpoint, later.)
 */
export const AgentNetworkWorkspace: React.FC<AgentNetworkWorkspaceProps> = ({
  onSelectAgent,
}) => {
  const agentsQ = useApi(() => intelligenceApi.agents());
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  if (agentsQ.loading) {
    return <div className="text-xs text-slate-400 font-mono p-8">Loading agent roster from /api/v1/agents…</div>;
  }
  if (agentsQ.error || !agentsQ.data) {
    return <Unavailable title="Agents unavailable" reason={agentsQ.error ?? "no agents payload"} />;
  }
  const adapted = adaptAgents(agentsQ.data);
  if ("unavailable" in adapted) {
    return <Unavailable title="Agents unavailable" reason={adapted.unavailable} />;
  }
  const agents = adapted;
  const currentAgent = agents.find(a => a.id === selectedAgentId) || agents[0];

  const handleInspectAgentById = (agentId: string) => {
    const target = agents.find(a => a.id === agentId);
    if (target) {
      setSelectedAgentId(target.id);
      onSelectAgent(target);
    }
  };

  const avgRep = agents.length > 0
    ? agents.reduce((acc, a) => acc + a.reputationScore, 0) / agents.length
    : null;

  return (
    <div className="space-y-4 pb-12 font-mono">
      {/* Header */}
      <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Users2 className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
              AI AGENT NETWORK & REPUTATION GOVERNANCE
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              FRAME 4
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Source: /api/v1/agents • Accuracy/IC need an evaluation feed (not published)
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">ACTIVE AGENTS:</span>{' '}
            <span className="text-cyan-300 font-bold">{agents.length} AGENTS ONLINE</span>
          </div>
          <div className="bg-white/[0.03] border border-white/[0.06] px-3 py-1.5 rounded">
            <span className="text-slate-400">AVG REPUTATION:</span>{' '}
            <span className="text-emerald-400 font-bold">
              {avgRep != null ? `${avgRep.toFixed(2)} (registry-reported)` : "—"}
            </span>
          </div>
        </div>
      </div>

      {/* Structured Multi-Agent Debate Feed Component */}
      <MultiAgentDebateFeed onInspectAgent={handleInspectAgentById} />

      {agents.length === 0 ? (
        <Unavailable
          title="No agents registered"
          reason="The agent roster is empty. Agents appear here once the communities register."
        />
      ) : (
        <>
          {/* Main Agent Topology & Network Visualizer */}
          <AgentNetworkVisualizer
            agents={agents}
            onSelectAgent={onSelectAgent}
          />

          {/* Agent Performance & Reputation Matrix Table */}
          <div className="bg-[#0d0f17] border border-white/[0.08] rounded-md p-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-2">
                <Award className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold uppercase text-white tracking-wider">
                  AGENT ROSTER & REPUTATION MATRIX
                </h3>
              </div>
              <span className="text-[10px] text-slate-400">SOURCE: /api/v1/agents</span>
            </div>

            <div className="overflow-x-auto my-3">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-white/[0.06] text-slate-500 text-[9px] uppercase tracking-wider">
                    <th className="py-2 px-2.5">AGENT NAME</th>
                    <th className="py-2 px-2">DOMAIN</th>
                    <th className="py-2 px-2">MODEL ARCHITECTURE</th>
                    <th className="py-2 px-2 text-right">REPUTATION</th>
                    <th className="py-2 px-2 text-right">ACCURACY</th>
                    <th className="py-2 px-2 text-right">CONFIDENCE</th>
                    <th className="py-2 px-2 text-right">LATENCY</th>
                    <th className="py-2 px-2">BIAS</th>
                    <th className="py-2 px-2 text-center">STATUS</th>
                    <th className="py-2 px-2 text-right">INSPECT</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.03]">
                  {agents.map((agent) => {
                    const isSelected = agent.id === currentAgent?.id;
                    return (
                      <tr
                        key={agent.id}
                        onClick={() => {
                          setSelectedAgentId(agent.id);
                          onSelectAgent(agent);
                        }}
                        className={`hover:bg-cyan-950/20 cursor-pointer transition-colors ${
                          isSelected ? 'bg-white/[0.04]' : ''
                        }`}
                      >
                        <td className="py-2.5 px-2.5 font-bold text-white flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                          {agent.name}
                        </td>
                        <td className="py-2.5 px-2 text-slate-300 text-[11px]">{agent.role}</td>
                        <td className="py-2.5 px-2 text-slate-400 font-mono text-[11px]">{agent.modelsUsed[0] ?? '—'}</td>
                        <td className="py-2.5 px-2 text-right font-mono-num font-bold text-cyan-300">
                          {agent.reputationScore.toFixed(2)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono-num text-slate-500">
                          —
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono-num text-slate-500">
                          —
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono-num text-slate-500">
                          —
                        </td>
                        <td className="py-2.5 px-2">
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            agent.bias === 'BULL'
                              ? 'bg-emerald-950/50 text-emerald-300 border border-emerald-800'
                              : agent.bias === 'BEAR'
                              ? 'bg-rose-950/50 text-rose-300 border border-rose-800'
                              : 'bg-white/[0.04] text-slate-400 border border-white/[0.06]'
                          }`}>
                            {agent.bias}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-center">
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 uppercase">
                            {agent.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectAgent(agent);
                            }}
                            className="text-[10px] text-cyan-400 hover:text-cyan-200 px-2 py-0.5 rounded bg-white/[0.04] border border-white/[0.08]"
                          >
                            Details →
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
