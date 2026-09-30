import React from 'react';
import {
  AgentNode,
  ExecutionOrder,
  IntelligenceItem,
  TimelineEvent,
} from '../../types';
import { CapitalTrajectoryChart } from '../CapitalTrajectoryChart';
import { IntelligenceStream } from '../IntelligenceStream';
import { CapitalAllocationMap } from '../CapitalAllocationMap';
import { RiskCommandSpectrum } from '../RiskCommandSpectrum';
import { AgentNetworkVisualizer } from '../AgentNetworkVisualizer';
import { LiveExecutionTape } from '../LiveExecutionTape';
import { MarketRegimeField } from '../MarketRegimeField';
import { DecisionProvenanceExplorer } from '../DecisionProvenanceExplorer';
import { Unavailable } from '../Unavailable';
import { useApi } from '../../hooks/useApi';
import { intelligenceApi, portfolioApi, riskApi, settingsApi } from '../../api/backend';
import { adaptEquity } from '../../adapters/equity';
import { adaptOpportunities } from '../../adapters/intelligence';
import { adaptPortfolio } from '../../adapters/portfolio';
import { adaptRisk } from '../../adapters/risk';
import { adaptAgents } from '../../adapters/agents';
import { adaptOrders } from '../../adapters/orders';
import { adaptRegimes } from '../../adapters/regimes';
import { adaptExecutionRowToTrace } from '../../adapters/executions';

interface CommandCanvasProps {
  onSelectEvent: (event: TimelineEvent) => void;
  onSelectIntelligence: (item: IntelligenceItem) => void;
  onSelectAgent: (agent: AgentNode) => void;
  onSelectOrder: (order: ExecutionOrder) => void;
  onSelectTrace: (traceId: string) => void;
  onOpenRiskWorkspace: () => void;
}

/**
 * Overview command canvas wired to live endpoints:
 * /equity, /opportunities, /portfolio, /risk (+/settings thresholds),
 * /agents, /orders, /regimes, /executions.
 * Full decision lineage loads on demand in the Provenance tab; here each
 * execution renders as an honest stub trace with unknowns marked.
 */
export const CommandCanvas: React.FC<CommandCanvasProps> = ({
  onSelectEvent,
  onSelectIntelligence,
  onSelectAgent,
  onSelectOrder,
  onSelectTrace,
  onOpenRiskWorkspace,
}) => {
  const equityQ = useApi(() => portfolioApi.equity());
  const intelQ = useApi(() => intelligenceApi.opportunities());
  const portfolioQ = useApi(() => portfolioApi.portfolio());
  const riskQ = useApi(() => riskApi.risk());
  const settingsQ = useApi(() => settingsApi.settings());
  const agentsQ = useApi(() => intelligenceApi.agents());
  const ordersQ = useApi(() => portfolioApi.orders());
  const regimesQ = useApi(() => intelligenceApi.regimes());
  const executionsQ = useApi(() => portfolioApi.executions());

  const loading =
    equityQ.loading || intelQ.loading || portfolioQ.loading || riskQ.loading ||
    agentsQ.loading || ordersQ.loading || regimesQ.loading || executionsQ.loading;
  if (loading) {
    return <div className="text-xs text-slate-400 font-mono p-8">Loading command canvas from live endpoints…</div>;
  }

  const firstError =
    equityQ.error ?? intelQ.error ?? portfolioQ.error ?? riskQ.error ??
    agentsQ.error ?? ordersQ.error ?? regimesQ.error ?? executionsQ.error;
  if (firstError || !equityQ.data || !portfolioQ.data || !riskQ.data || !agentsQ.data || !ordersQ.data || !regimesQ.data || !executionsQ.data || !intelQ.data) {
    return <Unavailable title="Overview unavailable" reason={firstError ?? "one or more command endpoints returned no payload"} />;
  }

  const trajectory = adaptEquity(equityQ.data);
  if ("unavailable" in trajectory) return <Unavailable title="Overview unavailable" reason={trajectory.unavailable} />;
  const intelligence = adaptOpportunities(intelQ.data);
  if ("unavailable" in intelligence) return <Unavailable title="Overview unavailable" reason={intelligence.unavailable} />;
  const allocation = adaptPortfolio(portfolioQ.data);
  if ("unavailable" in allocation) return <Unavailable title="Overview unavailable" reason={allocation.unavailable} />;
  const risk = adaptRisk(riskQ.data, settingsQ.data?.risk ?? null);
  if ("unavailable" in risk) return <Unavailable title="Overview unavailable" reason={risk.unavailable} />;
  const agents = adaptAgents(agentsQ.data);
  if ("unavailable" in agents) return <Unavailable title="Overview unavailable" reason={agents.unavailable} />;
  const orders = adaptOrders(ordersQ.data);
  if ("unavailable" in orders) return <Unavailable title="Overview unavailable" reason={orders.unavailable} />;
  const regimes = adaptRegimes(regimesQ.data);
  if ("unavailable" in regimes) return <Unavailable title="Overview unavailable" reason={regimes.unavailable} />;

  const traces = executionsQ.data.executions.map((e) => adaptExecutionRowToTrace(e)).flatMap((t) =>
    "unavailable" in t ? [] : [t],
  );

  return (
    <div className="space-y-4 pb-12">
      {/* Top Banner: Market State Field */}
      <MarketRegimeField instruments={regimes} />

      {/* Primary Workspace: Capital Trajectory + AI Intelligence Stream */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* Large Capital Trajectory Visualization Canvas (Primary Area) */}
        <div className="xl:col-span-8 space-y-4">
          <CapitalTrajectoryChart
            data={trajectory}
            onSelectEvent={onSelectEvent}
          />

          {/* Capital Allocation Workstation (Radial Map + Factors) */}
          <CapitalAllocationMap segments={allocation} />
        </div>

        {/* Intelligence Stream (Vertical Stream) */}
        <div className="xl:col-span-4">
          <IntelligenceStream
            items={intelligence}
            onSelectItem={onSelectIntelligence}
          />
        </div>
      </div>

      {/* Secondary Operational Row: Risk Command Center + Agent Debate Network */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        <div className="xl:col-span-6">
          <RiskCommandSpectrum
            risk={risk.spectrum}
            notComputed={risk.notComputed}
            onOpenRiskDrawer={onOpenRiskWorkspace}
          />
        </div>

        <div className="xl:col-span-6">
          <AgentNetworkVisualizer
            agents={agents}
            onSelectAgent={onSelectAgent}
          />
        </div>
      </div>

      {/* Decision Provenance & Execution Tape Row */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        <div className="xl:col-span-6">
          <DecisionProvenanceExplorer
            traces={traces}
            onSelectTrace={onSelectTrace}
          />
        </div>

        <div className="xl:col-span-6">
          <LiveExecutionTape
            orders={orders}
            onSelectOrder={onSelectOrder}
          />
        </div>
      </div>
    </div>
  );
};
