import  { useState, useEffect } from 'react';
import { 
  WorkspaceTab, 
  AutonomyLevel, 
  ExecutionMode, 
  Position, 
  AgentNode, 
   
  
  ExecutionOrder,
  SystemSettings
} from './types';
import {
  mockRiskSpectrum,
  mockAgents,
  mockPositions
} from './data/mockData';
import { DEFAULT_SYSTEM_SETTINGS } from './data/mockSettings';
import { TopSystemBar } from './components/TopSystemBar';
import { LeftIntelligenceRail } from './components/LeftIntelligenceRail';
import { PositionDrawer } from './components/PositionDrawer';
import { AgentDrawer } from './components/AgentDrawer';
import { CommandPaletteModal } from './components/CommandPaletteModal';
import { KillSwitchModal } from './components/KillSwitchModal';

// Workspace Views
import { CommandCanvas } from './components/views/CommandCanvas';
import { LiveTradingWorkspace } from './components/views/LiveTradingWorkspace';
import { PortfolioWorkspace } from './components/views/PortfolioWorkspace';
import { MarketIntelligenceWorkspace } from './components/views/MarketIntelligenceWorkspace';
import { AgentNetworkWorkspace } from './components/views/AgentNetworkWorkspace';
import { DecisionWorkspace } from './components/views/DecisionWorkspace';
import { RiskCommandCenterWorkspace } from './components/views/RiskCommandCenterWorkspace';
import { ExecutionWorkspace } from './components/views/ExecutionWorkspace';
import { StrategyResearchWorkspace } from './components/views/StrategyResearchWorkspace';
import { ModelGovernanceWorkspace } from './components/views/ModelGovernanceWorkspace';
import { AccountingTaxWorkspace } from './components/views/AccountingTaxWorkspace';
import { FinancialKernelWorkspace } from './components/views/FinancialKernelWorkspace';
import { AuditIntegrityWorkspace } from './components/views/AuditIntegrityWorkspace';
import { SystemHealthWorkspace } from './components/views/SystemHealthWorkspace';
import { DesignSystemWorkspace } from './components/views/DesignSystemWorkspace';
import { SettingsWorkspace } from './components/views/SettingsWorkspace';

export default function App() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('overview');
  
  // Persistent Settings
  const [settings, setSettings] = useState<SystemSettings>(() => {
    try {
      const stored = localStorage.getItem('aios0x_settings');
      if (stored) {
        return JSON.parse(stored);
      }
    } catch (e) {
      console.warn('Failed to load settings from storage', e);
    }
    return DEFAULT_SYSTEM_SETTINGS;
  });

  const [autonomy, setAutonomy] = useState<AutonomyLevel>(settings.autonomyLevel);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>(settings.defaultExecutionMode);

  // Interactive Data States (trading tab + drawers; wired tabs fetch their own)
  const [positions, setPositions] = useState<Position[]>(mockPositions);
  const [, setAgents] = useState<AgentNode[]>(mockAgents);
  const [, setExecutionOrders] = useState<ExecutionOrder[]>([]);
  const [riskSpectrum, setRiskSpectrum] = useState(mockRiskSpectrum);

  // Modals & Drawers
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<AgentNode | null>(null);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState<boolean>(false);
  const [isKillSwitchOpen, setIsKillSwitchOpen] = useState<boolean>(false);
  const [notificationToast, setNotificationToast] = useState<string | null>(null);

  // Synchronize settings changes
  const handleUpdateSettings = (newSettings: SystemSettings) => {
    setSettings(newSettings);
    setAutonomy(newSettings.autonomyLevel);
    setExecutionMode(newSettings.defaultExecutionMode);
    setRiskSpectrum(prev => ({
      ...prev,
      warningThresholdPct: newSettings.warningDrawdownPct,
      reductionThresholdPct: newSettings.deriskDrawdownPct,
      emergencyHaltPct: newSettings.emergencyHaltDrawdownPct,
      maxPositionConcentrationPct: newSettings.maxPositionConcentrationPct,
      maxClassExposurePct: newSettings.maxClassExposurePct,
    }));
    try {
      localStorage.setItem('aios0x_settings', JSON.stringify(newSettings));
    } catch (e) {
      console.warn('Failed to persist settings', e);
    }
  };

  const handleResetSettings = () => {
    handleUpdateSettings(DEFAULT_SYSTEM_SETTINGS);
  };

  const handleAutonomyChange = (lvl: AutonomyLevel) => {
    setAutonomy(lvl);
    setSettings(prev => ({ ...prev, autonomyLevel: lvl }));
  };

  const handleExecutionModeToggle = () => {
    const nextMode: ExecutionMode = executionMode === 'PAPER' ? 'LIVE' : 'PAPER';
    setExecutionMode(nextMode);
    setSettings(prev => ({ ...prev, defaultExecutionMode: nextMode }));
  };

  // Global Shortcut (⌘K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const triggerToast = (msg: string) => {
    setNotificationToast(msg);
    setTimeout(() => setNotificationToast(null), 4000);
  };

  // Handlers
  const handleAddExecutionOrder = (newOrder: ExecutionOrder) => {
    setExecutionOrders(prev => [newOrder, ...prev]);
    triggerToast(`Order dispatched: ${newOrder.side} ${newOrder.quantity} ${newOrder.symbol} via ${newOrder.venue}`);
  };

  const handleAddPosition = (newPos: Position) => {
    setPositions(prev => [newPos, ...prev]);
    triggerToast(`Recorded new position: ${newPos.side} ${newPos.size} ${newPos.symbol}`);
  };

  const handleTrimPosition = (posId: string, pct: number) => {
    setPositions(prev => prev.map(p => {
      if (p.id === posId) {
        const factor = (100 - pct) / 100;
        return {
          ...p,
          size: Math.round(p.size * factor),
          notionalUsd: Math.round(p.notionalUsd * factor),
          unrealizedPnlUsd: Math.round(p.unrealizedPnlUsd * factor),
        };
      }
      return p;
    }));
    triggerToast(`Position trimmed by ${pct}%. Order routed to TWAP execution slicer.`);
    setSelectedPosition(null);
  };

  const handleFlattenPosition = (posId: string) => {
    setPositions(prev => prev.filter(p => p.id !== posId));
    triggerToast('Position 100% flattened to USD Cash. Audit proof created.');
    setSelectedPosition(null);
  };

  const handleAdjustAgentWeight = (agentId: string, delta: number) => {
    setAgents(prev => prev.map(a => {
      if (a.id === agentId) {
        return {
          ...a,
          reputationScore: Math.min(1.0, Math.max(0.5, a.reputationScore + delta)),
        };
      }
      return a;
    }));
    triggerToast('Agent reputation weight recalibrated in LangGraph router.');
  };

  const handleConfirmKillSwitch = () => {
    setAutonomy('EMERGENCY_HALT');
    setPositions([]);
    setRiskSpectrum(prev => ({ ...prev, currentDrawdownPct: 0.0 }));
    setIsKillSwitchOpen(false);
    triggerToast('EMERGENCY HALT EXECUTED: All open orders cancelled. All positions flattened to USD.');
  };

  return (
    <div className="min-h-screen bg-[#050608] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/30 selection:text-cyan-200">
      {/* Persistent Institutional Top System Bar */}
      <TopSystemBar
        autonomy={autonomy}
        onAutonomyChange={handleAutonomyChange}
        executionMode={executionMode}
        onExecutionModeToggle={handleExecutionModeToggle}
        onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
        onTriggerKillSwitch={() => setIsKillSwitchOpen(true)}
        drawdownPct={riskSpectrum.currentDrawdownPct}
        chainVerified={true}
        onOpenSettings={() => setActiveTab('settings')}
        activeTab={activeTab}
      />

      <div className="flex-1 flex relative">
        {/* Persistent Slim Left Intelligence Rail */}
        <LeftIntelligenceRail
          activeTab={activeTab}
          onSelectTab={setActiveTab}
          pendingApprovalsCount={1}
          activeRiskWarnings={0}
        />

        {/* Main Content Workspace Container (offset for 56px fixed rail) */}
        <main className="flex-1 ml-14 p-4 sm:p-5 overflow-x-hidden min-h-[calc(100vh-44px)] min-w-0">
          {activeTab === 'overview' && (
            <CommandCanvas
              onSelectEvent={(evt) => triggerToast(`Inspecting event: ${evt.title}`)}
              onSelectIntelligence={(item) => triggerToast(`Focusing intelligence: ${item.headline}`)}
              onSelectAgent={(agent) => setSelectedAgent(agent)}
              onSelectOrder={(order) => triggerToast(`Inspecting order #${order.id} for ${order.symbol}`)}
              onSelectTrace={() => setActiveTab('provenance')}
              onOpenRiskWorkspace={() => setActiveTab('risk')}
            />
          )}

          {activeTab === 'trading' && (
            <LiveTradingWorkspace
              settings={settings}
              positions={positions}
              onAddOrder={handleAddExecutionOrder}
              onAddPosition={handleAddPosition}
              onClosePosition={handleFlattenPosition}
              onOpenSettings={() => setActiveTab('settings')}
              onTriggerToast={triggerToast}
            />
          )}

          {activeTab === 'portfolio' && (
            <PortfolioWorkspace
              onSelectPosition={(pos) => setSelectedPosition(pos)}
            />
          )}

          {activeTab === 'markets' && (
            <MarketIntelligenceWorkspace />
          )}

          {activeTab === 'agents' && (
            <AgentNetworkWorkspace
              onSelectAgent={(agent) => setSelectedAgent(agent)}
            />
          )}

          {activeTab === 'provenance' && (
            <DecisionWorkspace
              onSelectTrace={() => {}}
              onDispatchRatifiedOrder={(msg) => triggerToast(msg)}
            />
          )}

          {activeTab === 'risk' && (
            <RiskCommandCenterWorkspace />
          )}

          {activeTab === 'execution' && (
            <ExecutionWorkspace
              onSelectOrder={() => {}}
              onAddOrder={handleAddExecutionOrder}
            />
          )}

          {activeTab === 'research' && (
            <StrategyResearchWorkspace />
          )}

          {activeTab === 'strategies' && (
            <StrategyResearchWorkspace />
          )}

          {activeTab === 'models' && (
            <ModelGovernanceWorkspace />
          )}

          {activeTab === 'accounting' && (
            <AccountingTaxWorkspace />
          )}

          {activeTab === 'financial' && (
            <FinancialKernelWorkspace />
          )}

          {activeTab === 'audit' && (
            <AuditIntegrityWorkspace />
          )}

          {activeTab === 'system' && (
            <SystemHealthWorkspace />
          )}

          {activeTab === 'design_system' && (
            <DesignSystemWorkspace />
          )}

          {activeTab === 'settings' && (
            <SettingsWorkspace 
              settings={settings}
              onUpdateSettings={handleUpdateSettings}
              onResetDefaults={handleResetSettings}
              onTriggerToast={triggerToast}
            />
          )}
        </main>
      </div>

      {/* Global Interactive Drawers & Modals */}
      <PositionDrawer
        position={selectedPosition}
        onClose={() => setSelectedPosition(null)}
        onTrimPosition={handleTrimPosition}
        onFlattenPosition={handleFlattenPosition}
      />

      <AgentDrawer
        agent={selectedAgent}
        onClose={() => setSelectedAgent(null)}
        onAdjustWeight={handleAdjustAgentWeight}
      />

      <CommandPaletteModal
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onNavigate={setActiveTab}
        onSelectSymbol={(sym) => {
          triggerToast(`Navigated to ${sym} position & risk profile`);
        }}
      />

      <KillSwitchModal
        isOpen={isKillSwitchOpen}
        onClose={() => setIsKillSwitchOpen(false)}
        onConfirmKill={handleConfirmKillSwitch}
      />

      {/* Global Notification Toast */}
      {notificationToast && (
        <div className="fixed bottom-4 right-4 z-50 bg-[#0d0f17]/95 border border-cyan-500/50 rounded-lg p-3 shadow-2xl text-xs font-mono text-cyan-200 flex items-center gap-2.5 backdrop-blur-md animate-fade-in">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
          <span>{notificationToast}</span>
        </div>
      )}
    </div>
  );
}
