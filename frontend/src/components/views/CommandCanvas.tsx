import React from 'react';
import { 
  TrajectoryDataPoint, 
  IntelligenceItem, 
  AllocationSegment, 
  RiskSpectrum, 
  AgentNode, 
  ProvenanceTrace, 
  ExecutionOrder, 
  MarketRegimeItem,
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

interface CommandCanvasProps {
  trajectoryData: TrajectoryDataPoint[];
  intelligenceItems: IntelligenceItem[];
  allocationSegments: AllocationSegment[];
  riskSpectrum: RiskSpectrum;
  agents: AgentNode[];
  provenanceTraces: ProvenanceTrace[];
  executionOrders: ExecutionOrder[];
  marketRegimes: MarketRegimeItem[];
  onSelectEvent: (event: TimelineEvent) => void;
  onSelectIntelligence: (item: IntelligenceItem) => void;
  onSelectAgent: (agent: AgentNode) => void;
  onSelectOrder: (order: ExecutionOrder) => void;
  onSelectTrace: (traceId: string) => void;
  onOpenRiskWorkspace: () => void;
}

export const CommandCanvas: React.FC<CommandCanvasProps> = ({
  trajectoryData,
  intelligenceItems,
  allocationSegments,
  riskSpectrum,
  agents,
  provenanceTraces,
  executionOrders,
  marketRegimes,
  onSelectEvent,
  onSelectIntelligence,
  onSelectAgent,
  onSelectOrder,
  onSelectTrace,
  onOpenRiskWorkspace,
}) => {
  return (
    <div className="space-y-4 pb-12">
      {/* Top Banner: Market State Field */}
      <MarketRegimeField instruments={marketRegimes} />

      {/* Primary Workspace: Capital Trajectory + AI Intelligence Stream */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* Large Capital Trajectory Visualization Canvas (Primary Area) */}
        <div className="xl:col-span-8 space-y-4">
          <CapitalTrajectoryChart
            data={trajectoryData}
            onSelectEvent={onSelectEvent}
          />

          {/* Capital Allocation Workstation (Radial Map + Factors) */}
          <CapitalAllocationMap segments={allocationSegments} />
        </div>

        {/* Intelligence Stream (Vertical Stream) */}
        <div className="xl:col-span-4">
          <IntelligenceStream
            items={intelligenceItems}
            onSelectItem={onSelectIntelligence}
          />
        </div>
      </div>

      {/* Secondary Operational Row: Risk Command Center + Agent Debate Network */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        <div className="xl:col-span-6">
          <RiskCommandSpectrum
            risk={riskSpectrum}
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
            traces={provenanceTraces}
            onSelectTrace={onSelectTrace}
          />
        </div>

        <div className="xl:col-span-6">
          <LiveExecutionTape
            orders={executionOrders}
            onSelectOrder={onSelectOrder}
          />
        </div>
      </div>
    </div>
  );
};
