import { useState, useEffect, useMemo } from 'react';
import {
  WorkspaceTab,
  AutonomyLevel,
  ExecutionMode,
  Position,
  AgentNode,
} from './types';
import { EMPTY_SETTINGS, adaptSettingsV1 } from './adapters/settings';
import {
  settingsV1Api,
  approvalsApi,
  riskApi,
  auditApi,
  executiveApi,
  intelligenceApi,
  portfolioApi,
  researchApi,
} from './api/backend';
import { useApi } from './hooks/useApi';
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
import { ResearchWorkspace } from './components/views/ResearchWorkspace';
import { StrategyResearchWorkspace } from './components/views/StrategyResearchWorkspace';
import { CertificationWorkspace } from './components/views/CertificationWorkspace';
import { ModelGovernanceWorkspace } from './components/views/ModelGovernanceWorkspace';
import { AccountingTaxWorkspace } from './components/views/AccountingTaxWorkspace';
import { FinancialKernelWorkspace } from './components/views/FinancialKernelWorkspace';
import { AuditIntegrityWorkspace } from './components/views/AuditIntegrityWorkspace';
import { SystemHealthWorkspace } from './components/views/SystemHealthWorkspace';
import { DesignSystemWorkspace } from './components/views/DesignSystemWorkspace';
import { SettingsWorkspace } from './components/views/SettingsWorkspace';
import type { SystemSettings } from './types';

const SETTINGS_CACHE_KEY = 'aios0x_settings_cache_v1';

interface CachedSettings {
  version: number;
  settings: SystemSettings;
}

function readSettingsCache(): CachedSettings | null {
  try {
    const raw = localStorage.getItem(SETTINGS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedSettings;
    if (parsed && typeof parsed === 'object' && parsed.settings && typeof parsed.settings === 'object') {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('overview');

  // Server-owned settings (GET /api/v1/settings/v1 wins; localStorage is an
  // offline cache only). The Settings tab edits a working copy and PUTs it.
  const settingsQ = useApi(() => settingsV1Api.get());
  const [serverSettings, setServerSettings] = useState<SystemSettings>(() => {
    return readSettingsCache()?.settings ?? EMPTY_SETTINGS;
  });
  const [serverVersion, setServerVersion] = useState<number | null>(() => {
    return readSettingsCache()?.version ?? null;
  });

  useEffect(() => {
    if (!settingsQ.data) return;
    const adapted = adaptSettingsV1(settingsQ.data);
    if ("unavailable" in adapted) return;
    setServerSettings(adapted.settings);
    setServerVersion(adapted.version);
    try {
      localStorage.setItem(
        SETTINGS_CACHE_KEY,
        JSON.stringify({ version: adapted.version, settings: adapted.settings } satisfies CachedSettings),
      );
    } catch {
      // Offline cache is best-effort only.
    }
  }, [settingsQ.data]);

  const settingsPlaneAvailable =
    !!settingsQ.data && "available" in settingsQ.data && (settingsQ.data as { available: boolean }).available === true;
  const settingsPlaneReason =
    settingsQ.data && "available" in settingsQ.data && (settingsQ.data as { available: boolean }).available === false
      ? ((settingsQ.data as { available: false; reason?: string }).reason ?? settingsQ.error ?? "settings plane unavailable")
      : (settingsQ.error ?? null);

  // Live badge sources
  const approvalsQ = useApi(() => approvalsApi.approvals());
  const riskQ = useApi(() => riskApi.risk());
  const alertsQ = useApi(() => intelligenceApi.alerts());
  const verifyQ = useApi(() => auditApi.verify());
  const healthQ = useApi(() => executiveApi.health());
  const agentsQ = useApi(() => intelligenceApi.agents());
  const strategiesQ = useApi(() => portfolioApi.strategies());
  const knowledgeQ = useApi(() => researchApi.knowledge());

  const pendingApprovals = useMemo(() => {
    const list = approvalsQ.data?.approvals;
    return Array.isArray(list) ? list.length : null;
  }, [approvalsQ.data]);

  const riskWarnings = useMemo(() => {
    if (!riskQ.data && !alertsQ.data) return null;
    const compliance = Array.isArray(riskQ.data?.compliance_alerts) ? riskQ.data.compliance_alerts.length : 0;
    const emergency = Array.isArray(riskQ.data?.emergency_events) ? riskQ.data.emergency_events.length : 0;
    const alerts = Array.isArray(alertsQ.data?.alerts) ? alertsQ.data.alerts.length : 0;
    return compliance + emergency + alerts;
  }, [riskQ.data, alertsQ.data]);

  const drawdownPct = useMemo(() => {
    const v = riskQ.data?.drawdown_pct;
    return typeof v === "number" ? v : null;
  }, [riskQ.data]);

  const chainVerified = useMemo(() => {
    if (verifyQ.error || !verifyQ.data) return null;
    return verifyQ.data.valid === true;
  }, [verifyQ.data, verifyQ.error]);

  const systemWired = useMemo(() => {
    const comps = healthQ.data?.components;
    if (!comps) return null;
    const entries = Object.entries(comps);
    return `${entries.filter(([, v]) => v).length}/${entries.length}`;
  }, [healthQ.data]);

  const agentsCount = useMemo(() => {
    const list = agentsQ.data?.agents;
    return Array.isArray(list) ? list.length : null;
  }, [agentsQ.data]);

  const strategiesCount = useMemo(() => {
    const list = strategiesQ.data?.strategies;
    return Array.isArray(list) ? list.length : null;
  }, [strategiesQ.data]);

  const researchCount = useMemo(() => {
    const k = knowledgeQ.data;
    if (!k || k.available !== true) return null;
    return k.total ?? k.recent?.length ?? null;
  }, [knowledgeQ.data]);

  const [autonomy, setAutonomy] = useState<AutonomyLevel>(serverSettings.autonomyLevel);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>(serverSettings.defaultExecutionMode);

  // Follow the server blob when it (re)loads.
  useEffect(() => {
    setAutonomy(serverSettings.autonomyLevel);
    setExecutionMode(serverSettings.defaultExecutionMode);
  }, [serverSettings]);

  // Modals & Drawers
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<AgentNode | null>(null);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState<boolean>(false);
  const [isKillSwitchOpen, setIsKillSwitchOpen] = useState<boolean>(false);
  const [notificationToast, setNotificationToast] = useState<string | null>(null);

  const triggerToast = (msg: string) => {
    setNotificationToast(msg);
    setTimeout(() => setNotificationToast(null), 4000);
  };

  // Persist one settings blob server-side (PUT /api/v1/settings/v1).
  // 401 surfaces as an honest "operator token required" outcome.
  const handleSaveSettings = async (
    next: SystemSettings,
  ): Promise<{ ok: true; version: number } | { ok: false; reason: string; authRequired: boolean }> => {
    try {
      const result = await settingsV1Api.put(next as unknown as Record<string, unknown>);
      setServerSettings(next);
      setServerVersion(result.version);
      try {
        localStorage.setItem(SETTINGS_CACHE_KEY, JSON.stringify({ version: result.version, settings: next } satisfies CachedSettings));
      } catch {
        // Offline cache is best-effort only.
      }
      return { ok: true, version: result.version };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const authRequired = msg.includes("401") || msg.toLowerCase().includes("authentication");
      return { ok: false, reason: msg, authRequired };
    }
  };

  const handleResetSettings = async () => {
    const result = await handleSaveSettings(EMPTY_SETTINGS);
    if (result.ok) {
      triggerToast(`Settings reset to neutral defaults (server v${result.version}).`);
    } else {
      triggerToast(
        result.authRequired
          ? 'Reset blocked: operator token required (PUT answered 401).'
          : `Reset failed: ${result.reason}`,
      );
    }
  };

  // Top-bar governance toggles write through the same server PUT path.
  const handleAutonomyChange = async (lvl: AutonomyLevel) => {
    const prev = autonomy;
    setAutonomy(lvl);
    const result = await handleSaveSettings({ ...serverSettings, autonomyLevel: lvl });
    if (!result.ok) {
      setAutonomy(prev);
      triggerToast(
        result.authRequired
          ? 'Autonomy change blocked: operator token required (PUT answered 401).'
          : `Autonomy change failed: ${result.reason}`,
      );
    }
  };

  const handleExecutionModeToggle = async () => {
    const nextMode: ExecutionMode = executionMode === 'PAPER' ? 'LIVE' : 'PAPER';
    const prev = executionMode;
    setExecutionMode(nextMode);
    const result = await handleSaveSettings({ ...serverSettings, defaultExecutionMode: nextMode });
    if (!result.ok) {
      setExecutionMode(prev);
      triggerToast(
        result.authRequired
          ? 'Execution-mode change blocked: operator token required (PUT answered 401).'
          : `Execution-mode change failed: ${result.reason}`,
      );
    }
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

  // Position governance has no server-side flow — inspect only, honestly.
  const handleTrimPosition = () => {
    triggerToast('Trim not wired: no position-management endpoint exists server-side.');
  };

  const handleFlattenPosition = () => {
    triggerToast('Flatten not wired: no position-management endpoint exists server-side.');
  };

  const handleAdjustAgentWeight = () => {
    triggerToast('Agent weights are server-computed and not adjustable from this console.');
  };

  // The modal POSTs the real trigger_kill_switch action; on success the UI
  // follows the server into EMERGENCY_HALT and refreshes risk.
  const handleConfirmKillSwitch = () => {
    setAutonomy('EMERGENCY_HALT');
    setIsKillSwitchOpen(false);
    riskQ.refresh();
    triggerToast('Kill switch action accepted by the server. Risk state refreshing.');
  };

  return (
    <div className="min-h-screen bg-[var(--color-surface-deep)] text-text-strong flex flex-col font-sans selection:bg-accent selection:text-accent">
      {/* Persistent Institutional Top System Bar */}
      <TopSystemBar
        autonomy={autonomy}
        onAutonomyChange={handleAutonomyChange}
        executionMode={executionMode}
        onExecutionModeToggle={handleExecutionModeToggle}
        onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
        onTriggerKillSwitch={() => setIsKillSwitchOpen(true)}
        drawdownPct={drawdownPct}
        chainVerified={chainVerified}
        onOpenSettings={() => setActiveTab('settings')}
        activeTab={activeTab}
      />

      <div className="flex-1 flex relative">
        {/* Persistent Slim Left Intelligence Rail */}
        <LeftIntelligenceRail
          activeTab={activeTab}
          onSelectTab={setActiveTab}
          pendingApprovalsCount={pendingApprovals}
          activeRiskWarnings={riskWarnings}
          agentsCount={agentsCount}
          strategiesCount={strategiesCount}
          researchCount={researchCount}
          systemWired={systemWired}
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
              settings={serverSettings}
              onOpenSettings={() => setActiveTab('settings')}
              onTriggerToast={triggerToast}
              onInspectPosition={setSelectedPosition}
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
              onNotice={(msg) => triggerToast(msg)}
            />
          )}

          {activeTab === 'research' && (
            <ResearchWorkspace />
          )}

          {activeTab === 'strategies' && (
            <StrategyResearchWorkspace />
          )}

          {activeTab === 'certification' && (
            <CertificationWorkspace />
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
              settings={serverSettings}
              serverVersion={serverVersion}
              serverAvailable={settingsPlaneAvailable}
              serverReason={settingsPlaneReason}
              onSaveSettings={handleSaveSettings}
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
        <div className="fixed bottom-4 right-4 z-50 bg-[var(--color-surface-1)]//95 border border-accent rounded-lg p-3 shadow-2xl text-xs font-mono text-accent flex items-center gap-2.5 backdrop-blur-md animate-fade-in">
          <span className="w-2 h-2 rounded-full bg-accent animate-ping"></span>
          <span>{notificationToast}</span>
        </div>
      )}
    </div>
  );
}
